from calendar import timegm
from datetime import datetime
from inspect import isawaitable
from typing import Any, Type
from typing import Union, Optional
from typing import cast

import jwt
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.utils.translation import gettext as _
from graphql import GraphQLResolveInfo
from packaging.version import parse as parse_ver
from rest_framework.request import Request
from strawberry.annotation import StrawberryAnnotation  # type: ignore
from strawberry.arguments import StrawberryArgument
from strawberry.django.context import StrawberryDjangoContext
from strawberry.types import Info

from . import exceptions
from . import object_types
from .settings import jwt_settings


def create_strawberry_argument(
    python_name: str, graphql_name: str, type_: Type[Any], **options
):
    return StrawberryArgument(
        python_name,
        graphql_name,
        StrawberryAnnotation(create_argument_type(type_, **options)),
    )


def create_argument_type(type_: Type[Any], **options):
    if options.get("is_optional"):
        type_ = Optional[type_]  # type: ignore
    return type_


def jwt_payload(user, _=None):
    username = user.get_username()

    if hasattr(username, "pk"):
        username = username.pk

    exp = datetime.utcnow() + jwt_settings.JWT_EXPIRATION_DELTA

    payload = {
        user.USERNAME_FIELD: username,
        "exp": timegm(exp.utctimetuple()),
    }

    if jwt_settings.JWT_ALLOW_REFRESH:
        payload["origIat"] = timegm(datetime.utcnow().utctimetuple())

    if jwt_settings.JWT_AUDIENCE is not None:
        payload["aud"] = jwt_settings.JWT_AUDIENCE

    if jwt_settings.JWT_ISSUER is not None:
        payload["iss"] = jwt_settings.JWT_ISSUER

    return object_types.TokenPayloadType(**payload)


def jwt_encode(payload: object_types.TokenPayloadType, _=None) -> str:
    token = jwt.encode(
        payload.__dict__,
        jwt_settings.JWT_PRIVATE_KEY or jwt_settings.JWT_SECRET_KEY,
        jwt_settings.JWT_ALGORITHM,
    )
    _token = cast(str, token)
    if parse_ver(jwt.__version__) < parse_ver("2.0.0"):  # type: ignore
        _token = cast(bytes, _token).decode("utf8")
    return _token


def jwt_decode(token: str, _=None) -> object_types.TokenPayloadType:
    return object_types.TokenPayloadType(
        **jwt.decode(
            token,
            jwt_settings.JWT_PUBLIC_KEY or jwt_settings.JWT_SECRET_KEY,
            options={
                "verify_exp": jwt_settings.JWT_VERIFY_EXPIRATION,
                "verify_aud": jwt_settings.JWT_AUDIENCE is not None,
                "verify_signature": jwt_settings.JWT_VERIFY,
            },
            leeway=jwt_settings.JWT_LEEWAY,
            audience=jwt_settings.JWT_AUDIENCE,
            issuer=jwt_settings.JWT_ISSUER,
            algorithms=[jwt_settings.JWT_ALGORITHM],
        )
    )


def get_http_authorization(context):
    req = get_context(context)
    auth = req.META.get(jwt_settings.JWT_AUTH_HEADER_NAME, "").split()
    prefix = jwt_settings.JWT_AUTH_HEADER_PREFIX

    if len(auth) != 2 or auth[0].lower() != prefix.lower():
        return req.COOKIES.get(jwt_settings.JWT_COOKIE_NAME)
    return auth[1]


def get_token_argument(_, **kwargs):
    if jwt_settings.JWT_ALLOW_ARGUMENT:
        input_fields = kwargs.get("input")

        if isinstance(input_fields, dict):
            kwargs = input_fields

        return kwargs.get(jwt_settings.JWT_ARGUMENT_NAME)
    return None


# def get_token_argument(field_node, variable_values, **kwargs):
#     if jwt_settings.JWT_ALLOW_ARGUMENT:
#         if field_node.arguments is not None and len(field_node.arguments) > 0:
#             for arg in field_node.arguments:
#                 if arg.name.value == jwt_settings.JWT_ARGUMENT_NAME:
#                     if 'value' not in arg.value.keys:
#                         return variable_values.get(arg.value.name.value)
#                     return arg.value.value
#
#     return None


def get_credentials(request, **kwargs):
    return get_token_argument(request, **kwargs) or get_http_authorization(request)


def get_payload(token, context=None):
    try:
        payload = jwt_settings.JWT_DECODE_HANDLER(token, context)
    except jwt.ExpiredSignatureError:
        raise exceptions.JSONWebTokenExpired()
    except jwt.DecodeError:
        raise exceptions.JSONWebTokenError(_("Error decoding signature"))
    except jwt.InvalidTokenError:
        raise exceptions.JSONWebTokenError(_("Invalid token"))
    return payload


def get_user_by_natural_key(username):
    user_model = get_user_model()
    try:
        return user_model.objects.get_by_natural_key(username)
    except user_model.DoesNotExist:
        return None


async def get_user_by_natural_key_async(username):
    user_model = get_user_model()
    try:
        return await sync_to_async(user_model.objects.get_by_natural_key)(username)
    except user_model.DoesNotExist:
        return None


def get_user_by_payload(payload):
    username = jwt_settings.JWT_PAYLOAD_GET_USERNAME_HANDLER(payload)

    if not username:
        raise exceptions.JSONWebTokenError(_("Invalid payload"))

    user = jwt_settings.JWT_GET_USER_BY_NATURAL_KEY_HANDLER(username)

    if user is not None and not getattr(user, "is_active", True):
        raise exceptions.JSONWebTokenError(_("User is disabled"))
    return user


async def get_user_by_payload_async(payload):
    username = jwt_settings.JWT_PAYLOAD_GET_USERNAME_HANDLER(payload)

    if not username:
        raise exceptions.JSONWebTokenError(_("Invalid payload"))

    user = await jwt_settings.JWT_ASYNC_GET_USER_BY_NATURAL_KEY_HANDLER(username)

    if user is not None and not getattr(user, "is_active", True):
        raise exceptions.JSONWebTokenError(_("User is disabled"))
    return user


def refresh_has_expired(orig_iat, _=None):
    exp = orig_iat + jwt_settings.JWT_REFRESH_EXPIRATION_DELTA.total_seconds()
    return timegm(datetime.utcnow().utctimetuple()) > exp


def set_cookie(response, key, value, expires):
    kwargs = {
        "expires": expires,
        "httponly": True,
        "secure": jwt_settings.JWT_COOKIE_SECURE,
        "path": jwt_settings.JWT_COOKIE_PATH,
        "domain": jwt_settings.JWT_COOKIE_DOMAIN,
        "samesite": jwt_settings.JWT_COOKIE_SAMESITE,
    }
    response.set_cookie(key, value, **kwargs)


def delete_cookie(response, key):
    response.delete_cookie(
        key,
        path=jwt_settings.JWT_COOKIE_PATH,
        domain=jwt_settings.JWT_COOKIE_DOMAIN,
    )


def await_and_execute(obj, on_resolve):
    async def build_resolve_async():
        return on_resolve(await obj)

    return build_resolve_async()


def maybe_thenable(obj, on_resolve):
    """
    Execute a on_resolve function once the thenable is resolved,
    returning the same type of object inputted.
    If the object is not thenable, it should return on_resolve(obj)
    """
    if isawaitable(obj):
        return await_and_execute(obj, on_resolve)

    # If it's not awaitable, return the function executed over the object
    return on_resolve(obj)


def get_context(
    info: Union[HttpRequest, Request, Info[Any, Any], GraphQLResolveInfo]
) -> Any:
    if hasattr(info, "context"):
        ctx = getattr(info, "context")
        if isinstance(ctx, StrawberryDjangoContext):
            return ctx.request
        return ctx
    return info
