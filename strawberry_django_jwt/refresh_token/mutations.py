import strawberry
from strawberry.types import Info

from ..object_types import DeleteType
from ..settings import jwt_settings
from ..utils import get_context
from .decorators import ensure_refresh_token
from .object_types import RevokeType
from .shortcuts import get_refresh_token


class Revoke:
    @strawberry.mutation
    @ensure_refresh_token
    def revoke(self, info: Info, refresh_token: str) -> RevokeType:
        context = info.context
        refresh_token_obj = get_refresh_token(refresh_token, context)
        refresh_token_obj.revoke(context)
        return RevokeType(revoked=refresh_token_obj.revoked)


class DeleteRefreshTokenCookie:
    @strawberry.mutation
    def delete_cookie(self, info: Info) -> DeleteType:
        ctx = get_context(info)
        ctx.delete_refresh_token_cookie = (
            jwt_settings.JWT_REFRESH_TOKEN_COOKIE_NAME in ctx.COOKIES
            and getattr(ctx, "jwt_cookie", False)
        )
        return DeleteType(deleted=ctx.delete_refresh_token_cookie)
