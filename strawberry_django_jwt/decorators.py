import inspect
from calendar import timegm
from datetime import datetime
from functools import wraps

import django.contrib.auth.base_user
import strawberry
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.core.handlers.asgi import ASGIRequest
from django.middleware.csrf import rotate_token
from django.utils.translation import gettext as _
from strawberry.types import Info
from strawberry_django.utils import is_async

from . import exceptions
from . import signals
from .auth import authenticate
from .refresh_token.shortcuts import create_refresh_token, refresh_token_lazy_async
from .refresh_token.shortcuts import refresh_token_lazy
from .settings import jwt_settings
from .utils import delete_cookie
from .utils import get_context
from .utils import maybe_thenable
from .utils import set_cookie

__all__ = [
    "user_passes_test",
    "login_required",
    "staff_member_required",
    "superuser_required",
    "permission_required",
    "refresh_expiration",
    "token_auth",
    "csrf_rotation",
    "setup_jwt_cookie",
    "jwt_cookie",
    "ensure_token",
    "dispose_extra_kwargs",
    "login_field",
]


def with_info(target):
    def signature_add_fn(self, info: Info, *args, **kwargs):
        # Only called when no info should be passed, no need to check
        return target(self, *args, **kwargs)

    # Create a fake target function with info argument
    target_inspection = inspect.signature(target)
    target_clean = target
    if "info" not in target_inspection.parameters.keys():
        signature_add_fn.__signature__ = inspect.Signature(
            [
                *target_inspection.parameters.values(),
                inspect.Parameter("info", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ],
            return_annotation=target_inspection.return_annotation,
        )
        # Copy annotations as well
        signature_add_fn.__annotations__ = target.__annotations__
        target_clean = signature_add_fn
    return target_clean


def context(func):
    def wrapper(*args, **kwargs):
        info = kwargs.get("info")
        ctx = get_context(info)
        return func(ctx, *args, **kwargs)

    return wrapper


def user_passes_test(test_func, exc=exceptions.PermissionDenied):
    def decorator(f):
        # get_result is used by strawberry-graphql-django model mutations
        get_result = getattr(f, "get_result", None)

        if get_result is not None and callable(get_result):
            f.get_result = decorator(f.get_result)
            return f

        f_with_info = with_info(f)

        @wraps(f_with_info)
        @context
        def wrapper(context, *args, **kwargs):
            if context and test_func(context.user):
                return dispose_extra_kwargs(f_with_info)(*args, **kwargs)
            raise exc

        return wrapper

    return decorator


staff_member_required = user_passes_test(lambda u: u.is_staff)
superuser_required = user_passes_test(lambda u: u.is_superuser)
login_required = user_passes_test(lambda u: u.is_authenticated)


def login_field(fn=None):
    return strawberry.field(login_required(fn))


def permission_required(perm):
    def check_perms(user):
        if isinstance(perm, str):
            perms = (perm,)
        else:
            perms = perm
        return user.has_perms(perms)

    return user_passes_test(check_perms)


def on_token_auth_resolve(values):
    info, user, payload = values
    ctx = get_context(info)
    payload.payload = jwt_settings.JWT_PAYLOAD_HANDLER(user, ctx)
    payload.token = jwt_settings.JWT_ENCODE_HANDLER(payload.payload, ctx)

    if jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN:
        if getattr(ctx, "jwt_cookie", False):
            ctx.jwt_refresh_token = create_refresh_token(user)
            payload.refresh_token = ctx.jwt_refresh_token.get_token()
        else:
            payload.refresh_token = refresh_token_lazy(user)

    return payload


async def on_token_auth_resolve_async(values):
    info, user, payload = values
    ctx = get_context(info)
    payload.payload = jwt_settings.JWT_PAYLOAD_HANDLER(user, ctx)
    payload.token = jwt_settings.JWT_ENCODE_HANDLER(payload.payload, ctx)

    if jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN:
        if getattr(ctx, "jwt_cookie", False):
            ctx.jwt_refresh_token = await sync_to_async(create_refresh_token)(user)
            payload.refresh_token = ctx.jwt_refresh_token.get_token()
        else:
            payload.refresh_token = await refresh_token_lazy_async(user)

    return payload


def token_auth(f):
    async def wrapper_async(cls, info, password, **kwargs):
        context = get_context(info)
        context._jwt_token_auth = True
        username = kwargs.get(get_user_model().USERNAME_FIELD)
        user = await authenticate(
            request=context,
            username=username,
            password=password,
        )
        if user is None:
            raise exceptions.JSONWebTokenError(
                _("Please enter valid credentials"),
            )

        context.user = user

        result = f(cls, info, **kwargs)
        signals.token_issued.send(sender=cls, request=context, user=user)
        return await maybe_thenable((info, user, result), on_token_auth_resolve_async)

    @wraps(f)
    @setup_jwt_cookie
    @csrf_rotation
    @refresh_expiration
    def wrapper(cls, info, password, **kwargs):
        context = get_context(info)
        if inspect.isawaitable(f) or (isinstance(context, ASGIRequest) and is_async()):
            return wrapper_async(cls, info, password, **kwargs)
        context._jwt_token_auth = True
        username = kwargs.get(get_user_model().USERNAME_FIELD)
        user = django.contrib.auth.authenticate(
            request=context,
            username=username,
            password=password,
        )
        if user is None:
            raise exceptions.JSONWebTokenError(
                _("Please enter valid credentials"),
            )

        context.user = user

        result = f(cls, info, **kwargs)
        signals.token_issued.send(sender=cls, request=context, user=user)
        return maybe_thenable((info, user, result), on_token_auth_resolve)

    return wrapper


def refresh_expiration(f):
    @wraps(f)
    def wrapper(cls, *args, **kwargs):
        def on_resolve(payload):
            payload.refresh_expires_in = (
                timegm(datetime.utcnow().utctimetuple())
                + jwt_settings.JWT_REFRESH_EXPIRATION_DELTA.total_seconds()
            )
            return payload

        result = f(cls, *args, **kwargs)
        return maybe_thenable(result, on_resolve)

    return wrapper


def csrf_rotation(f):
    @wraps(f)
    def wrapper(cls, info, *args, **kwargs):
        result = f(cls, info, **kwargs)

        if jwt_settings.JWT_CSRF_ROTATION:
            rotate_token(info.context)
        return result

    return wrapper


def setup_jwt_cookie(f):
    async def set_token(ctx, result):
        res = await result
        setattr(ctx, "jwt_token", res.token)
        return res

    @wraps(f)
    def wrapper(cls, info, *args, **kwargs):
        result = f(cls, info, **kwargs)
        ctx = get_context(info)
        if getattr(ctx, "jwt_cookie", False):
            if inspect.isawaitable(result):
                return set_token(ctx, result)
            else:
                ctx.jwt_token = result.token
        return result

    return wrapper


def jwt_cookie(view_func):
    async def finish_response(request, response):
        res = await response
        return finish_response_sync(request, res)

    def finish_response_sync(request, response):
        if hasattr(request, "jwt_token"):
            expires = datetime.utcnow() + jwt_settings.JWT_EXPIRATION_DELTA

            set_cookie(
                response,
                jwt_settings.JWT_COOKIE_NAME,
                request.jwt_token,
                expires=expires,
            )
            if hasattr(request, "jwt_refresh_token"):
                refresh_token = request.jwt_refresh_token
                expires = (
                    refresh_token.created + jwt_settings.JWT_REFRESH_EXPIRATION_DELTA
                )

                set_cookie(
                    response,
                    jwt_settings.JWT_REFRESH_TOKEN_COOKIE_NAME,
                    refresh_token.token,
                    expires=expires,
                )

        if hasattr(request, "delete_jwt_cookie"):
            delete_cookie(response, jwt_settings.JWT_COOKIE_NAME)

        if hasattr(request, "delete_refresh_token_cookie"):
            delete_cookie(response, jwt_settings.JWT_REFRESH_TOKEN_COOKIE_NAME)

        return response

    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        request.jwt_cookie = True
        response = view_func(request, *args, **kwargs)

        if inspect.isawaitable(response):
            return finish_response(request, response)

        return finish_response_sync(request, response)

    return wrapped_view


def ensure_token(f):
    @wraps(f)
    def wrapper(cls, info, token=None, *args, **kwargs):
        if token is None:
            cookies = get_context(info).COOKIES
            token = cookies.get(jwt_settings.JWT_COOKIE_NAME)

            if token is None:
                raise exceptions.JSONWebTokenError(_("Token is required"))
        return f(cls, info, token, *args, **kwargs)

    return wrapper


def dispose_extra_kwargs(fn):
    @wraps(fn)
    def wrapper(src, *args_, **kwargs_):
        root = {}
        if src:
            args_ = args_[1:]
        present = inspect.signature(fn).parameters.keys()
        for key, val in kwargs_.items():
            if key not in present:
                root[key] = val
        passed_kwargs = {k: v for k, v in kwargs_.items() if k in present}
        if src:
            return fn(src, root, *args_, **passed_kwargs)
        if not root:
            return fn(src, *args_, **passed_kwargs)
        return fn(root, *args_, **passed_kwargs)

    return wrapper
