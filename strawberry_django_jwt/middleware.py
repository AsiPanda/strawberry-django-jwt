from inspect import isawaitable
from typing import Any, Set, cast

from django.contrib.auth import authenticate
from django.contrib.auth.middleware import get_user
from django.contrib.auth.models import AnonymousUser
from django.utils.translation import gettext as _
from graphql import GraphQLResolveInfo, GraphQLType
from strawberry.extensions import Extension
from strawberry.types import ExecutionContext

from strawberry_django_jwt import exceptions
from strawberry_django_jwt.auth import authenticate as authenticate_async
from strawberry_django_jwt.path import PathDict
from strawberry_django_jwt.settings import jwt_settings
from strawberry_django_jwt.utils import (
    get_context,
    get_http_authorization,
    get_token_argument,
)

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

    def resolve_base(self, info: GraphQLResolveInfo, **kwargs):
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

        if (_authenticate(context) or token_argument is not None) and self.authenticate_context(
            info, **kwargs
        ):
            return context, token_argument
        elif (
            info.field_name == "__schema"
            and cast(GraphQLResolveInfo, info).parent_type.name == "Query"
            and jwt_settings.JWT_AUTHENTICATE_INTROSPECTION
            and self.authenticate_context(info, **kwargs)
        ):

            raise exceptions.PermissionDenied(_("The introspection query requires authentication."))

        return context, token_argument


class JSONWebTokenMiddleware(BaseJSONWebTokenMiddleware):
    def resolve(self, _next, root, info: GraphQLResolveInfo, *args, **kwargs):
        context, token_argument = self.resolve_base(info, **kwargs)

        if (_authenticate(context) or token_argument is not None) and self.authenticate_context(
            info, **kwargs
        ):

            user = authenticate(request=context, **kwargs)

            if user is not None:
                context.user = user

                if jwt_settings.JWT_ALLOW_ARGUMENT:
                    self.cached_authentication.insert(info.path, user)

        return _next(root, info, **kwargs)


class AsyncJSONWebTokenMiddleware(BaseJSONWebTokenMiddleware):
    async def resolve(self, _next, root, info: GraphQLResolveInfo, *args, **kwargs):
        context, token_argument = self.resolve_base(info, **kwargs)

        if (_authenticate(context) or token_argument is not None) and self.authenticate_context(
            info, **kwargs
        ):

            user = await authenticate_async(request=context, **kwargs)

            if user is not None:
                context.user = user

                if jwt_settings.JWT_ALLOW_ARGUMENT:
                    self.cached_authentication.insert(info.path, user)

        result = _next(root, info, **kwargs)
        if isawaitable(result):
            return await result
        return result
