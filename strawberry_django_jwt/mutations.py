import inspect

from django.contrib.auth import get_user_model
import strawberry
from strawberry.field import StrawberryField
from strawberry.types import Info

from . import mixins
from .decorators import dispose_extra_kwargs, ensure_token, token_auth
from .object_types import DeleteType, PayloadType, TokenDataType, TokenPayloadType
from .refresh_token.mutations import DeleteRefreshTokenCookie, Revoke

__all__ = [
    "JSONWebTokenMutation",
    "ObtainJSONWebToken",
    "Verify",
    "Refresh",
    "Revoke",
    "DeleteRefreshTokenCookie",
    "DeleteJSONWebTokenCookie",
]

from .settings import jwt_settings
from .utils import create_strawberry_argument, get_context, get_payload


class JSONWebTokenMutation(mixins.JSONWebTokenMixin):
    def __init_subclass__(cls):
        super().__init_subclass__()
        user = get_user_model().USERNAME_FIELD
        field: StrawberryField
        for (_, field) in inspect.getmembers(cls, lambda f: isinstance(f, StrawberryField)):
            field.arguments.extend(
                [
                    create_strawberry_argument(user, user, str),
                    create_strawberry_argument("password", "password", str),
                ]
            )


class ObtainJSONWebToken(JSONWebTokenMutation):
    """
    Obtain JSON Web Token mutation.
    """

    @strawberry.mutation
    @token_auth
    @dispose_extra_kwargs
    def obtain(self, info: Info) -> TokenDataType:
        return TokenDataType(payload=TokenPayloadType())


class Verify:
    @strawberry.mutation
    @ensure_token
    def verify(self, info: Info, token: str) -> PayloadType:
        return PayloadType(payload=get_payload(token, info.context))


class Refresh(mixins.RefreshMixin):
    pass


class DeleteJSONWebTokenCookie:
    @strawberry.mutation
    def delete_cookie(self, info: Info) -> DeleteType:
        ctx = get_context(info)
        ctx.delete_jwt_cookie = jwt_settings.JWT_COOKIE_NAME in ctx.COOKIES and ctx.jwt_cookie

        return DeleteType(deleted=ctx.delete_jwt_cookie)
