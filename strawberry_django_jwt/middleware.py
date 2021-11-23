from inspect import isawaitable
from typing import Set, Any

from django.contrib.auth import authenticate
from django.contrib.auth.middleware import get_user
from django.contrib.auth.models import AnonymousUser
from graphql import GraphQLType
from strawberry.extensions import Extension
from strawberry.types import ExecutionContext

from .auth import authenticate as authenticate_async
from .path import PathDict
from .settings import jwt_settings
from .utils import get_context
from .utils import get_http_authorization
from .utils import get_token_argument

__all__ = [
    "allow_any",
    "JSONWebTokenMiddleware",
    "AsyncJSONWebTokenMiddleware",
]


def allow_any(info, **kwargs):
    field = info.parent_type.fields.get(info.field_name)

    if field is None:
        return False

    field_type = getattr(field.type, "of_type", None)

    return field_type is not None and any(
        [
            issubclass(class_type, GraphQLType) and isinstance(field_type, class_type)
            for class_type in tuple(jwt_settings.JWT_ALLOW_ANY_CLASSES)
        ]
    )


def _authenticate(request):
    is_anonymous = not hasattr(request, "user") or request.user.is_anonymous
    return is_anonymous and get_http_authorization(request) is not None


class BaseJSONWebTokenMiddleware(Extension):
    def __init__(self, *, execution_context: ExecutionContext):
        super().__init__(execution_context=execution_context)
        self.cached_allow_any: Set[Any] = set()

        if jwt_settings.JWT_ALLOW_ARGUMENT:
            self.cached_authentication = PathDict()

    def authenticate_context(self, info, **kwargs):
        root_path = info.path[0]

        if root_path not in self.cached_allow_any:
            if jwt_settings.JWT_ALLOW_ANY_HANDLER(info, **kwargs):
                self.cached_allow_any.add(root_path)
            else:
                return True
        return False


class JSONWebTokenMiddleware(BaseJSONWebTokenMiddleware):
    def resolve(self, next_, root, info, **kwargs):
        context = get_context(info)
        token_argument = get_token_argument(context, **kwargs)

        if jwt_settings.JWT_ALLOW_ARGUMENT and token_argument is None:
            user = self.cached_authentication.parent(info.path)

            if user is not None:
                context.user = user

            elif hasattr(context, "user"):
                if hasattr(context, "session"):
                    context.user = get_user(context)
                    self.cached_authentication.insert(info.path, context.user)
                else:
                    context.user = AnonymousUser()

        if (
            _authenticate(context) or token_argument is not None
        ) and self.authenticate_context(info, **kwargs):

            user = authenticate(request=context, **kwargs)

            if user is not None:
                context.user = user

                if jwt_settings.JWT_ALLOW_ARGUMENT:
                    self.cached_authentication.insert(info.path, user)

        return next_(root, info, **kwargs)


class AsyncJSONWebTokenMiddleware(BaseJSONWebTokenMiddleware):
    async def resolve(self, next_, root, info, **kwargs):
        context = get_context(info)
        token_argument = get_token_argument(context, **kwargs)

        if jwt_settings.JWT_ALLOW_ARGUMENT and token_argument is None:
            user = self.cached_authentication.parent(info.path)

            if user is not None:
                context.user = user

            elif hasattr(context, "user"):
                if hasattr(context, "session"):
                    context.user = get_user(context)
                    self.cached_authentication.insert(info.path, context.user)
                else:
                    context.user = AnonymousUser()

        if (
            _authenticate(context) or token_argument is not None
        ) and self.authenticate_context(info, **kwargs):

            user = await authenticate_async(request=context, **kwargs)

            if user is not None:
                context.user = user

                if jwt_settings.JWT_ALLOW_ARGUMENT:
                    self.cached_authentication.insert(info.path, user)

        result = next_(root, info, **kwargs)
        if isawaitable(result):
            return await result
        return result
