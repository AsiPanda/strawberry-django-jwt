from asgiref.sync import sync_to_async
from django.utils.functional import lazy
from django.utils.translation import gettext as _

from strawberry_django_jwt.exceptions import JSONWebTokenError
from strawberry_django_jwt.refresh_token.models import AbstractRefreshToken
from strawberry_django_jwt.refresh_token.utils import get_refresh_token_model
from strawberry_django_jwt.settings import jwt_settings


def get_refresh_token(token, context=None):
    refresh_token_model = get_refresh_token_model()

    try:
        return jwt_settings.JWT_GET_REFRESH_TOKEN_HANDLER(
            refresh_token_model=refresh_token_model,
            token=token,
            context=context,
        )

    except refresh_token_model.DoesNotExist:
        raise JSONWebTokenError(_("Invalid refresh token"))


def create_refresh_token(user, refresh_token=None) -> AbstractRefreshToken:
    if refresh_token is not None and jwt_settings.JWT_REUSE_REFRESH_TOKENS:
        refresh_token.reuse()
        return refresh_token
    return get_refresh_token_model().objects.create(user=user)


refresh_token_lazy = lazy(
    lambda user, refresh_token=None: create_refresh_token(user, refresh_token).get_token(),
    str,
)


async def create_token_lazy_async(user, refresh_token=None):
    res = await sync_to_async(create_refresh_token)(user, refresh_token)
    return res.get_token()


refresh_token_lazy_async = create_token_lazy_async
