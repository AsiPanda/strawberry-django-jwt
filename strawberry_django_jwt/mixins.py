import inspect
from typing import Any
from typing import Dict
from typing import Optional
from typing import TYPE_CHECKING

import strawberry
from django.utils.translation import gettext as _
from strawberry.arguments import StrawberryArgument
from strawberry.field import StrawberryField

from . import exceptions
from . import settings
from .decorators import csrf_rotation
from .decorators import ensure_token
from .decorators import refresh_expiration
from .decorators import setup_jwt_cookie
from .fields import ExtendedStrawberryField
from .object_types import TokenDataType
from .object_types import TokenPayloadType
from .refresh_token import signals as refresh_signals
from .refresh_token.decorators import ensure_refresh_token
from .refresh_token.object_types import RefreshedTokenType
from .refresh_token.shortcuts import create_refresh_token
from .refresh_token.shortcuts import get_refresh_token
from .refresh_token.shortcuts import refresh_token_lazy
from .signals import token_refreshed
from .utils import get_payload
from .utils import get_user_by_payload
from .utils import maybe_thenable


class RequestInfoMixin:
    def __init_subclass__(cls):
        super().__init_subclass__()
        field: StrawberryField
        for (_, field) in inspect.getmembers(cls, lambda f: isinstance(f, StrawberryField)):
            field.__class__ = ExtendedStrawberryField


class BaseJSONWebTokenMixin:
    @staticmethod
    def init_fields(cls, field_options: Optional[Dict[str, Dict[str, Any]]] = None):
        if field_options is None:
            field_options = {}
        if not settings.jwt_settings.JWT_HIDE_TOKEN_FIELDS:
            for (name, field) in inspect.getmembers(cls, lambda f: isinstance(f, StrawberryField)):
                field.arguments.append(StrawberryArgument(
                    "token", "token", str, **field_options.get("token", {})))
                if settings.jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN:
                    field.arguments.append(
                        StrawberryArgument("refresh_token", "refresh_token", str,
                                           **field_options.get("refresh_token", {})))
                # field.base_resolver.wrapped_func = strip_kwargs(field.base_resolver.wrapped_func,
                #                                                 ["token", "refresh_token"])


class JSONWebTokenMixin(BaseJSONWebTokenMixin):
    def __init_subclass__(cls, **kwargs):
        cls.init_fields(cls)


class OptionalJSONWebTokenMixin(BaseJSONWebTokenMixin):
    def __init_subclass__(cls, **kwargs):
        cls.init_fields(cls, {"token": {"is_optional": True},
                              "refresh_token": {"is_optional": True}})


class BaseRefreshMixin:
    @strawberry.mutation
    @setup_jwt_cookie
    @csrf_rotation
    @ensure_token
    def refresh(self, info, token: Optional[str]) -> TokenDataType:
        return TokenDataType(payload=TokenPayloadType())


class KeepAliveRefreshMixin(BaseRefreshMixin, OptionalJSONWebTokenMixin):
    @strawberry.mutation
    @setup_jwt_cookie
    @csrf_rotation
    @ensure_token
    def refresh(self, info, token: Optional[str]) -> TokenDataType:
        def on_resolve(values):
            payload, token = values
            payload.token = token
            return payload

        context = info.context
        payload = get_payload(token, context)
        user = get_user_by_payload(payload)
        orig_iat = payload.origIat

        if orig_iat is None:
            raise exceptions.JSONWebTokenError(_('origIat field is required'))

        if settings.jwt_settings.JWT_REFRESH_EXPIRED_HANDLER(orig_iat, context):
            raise exceptions.JSONWebTokenError(_('Refresh has expired'))

        payload = settings.jwt_settings.JWT_PAYLOAD_HANDLER(user, context)
        payload.origIat = orig_iat
        refresh_expires_in = orig_iat + \
            settings.jwt_settings.JWT_REFRESH_EXPIRATION_DELTA.total_seconds()

        token = settings.jwt_settings.JWT_ENCODE_HANDLER(
            payload, context) or ""
        token_refreshed.send(
            sender=RefreshMixin, request=context, user=user)

        result = TokenDataType(payload, token, refresh_expires_in)
        return maybe_thenable((result, token), on_resolve)


class RefreshTokenMixin(BaseRefreshMixin, OptionalJSONWebTokenMixin, RequestInfoMixin):
    @strawberry.mutation
    @setup_jwt_cookie
    @csrf_rotation
    @refresh_expiration
    @ensure_refresh_token
    def refresh(self, info, refresh_token: Optional[str]) -> RefreshedTokenType:
        context = info.context
        old_refresh_token = get_refresh_token(refresh_token, context)

        if old_refresh_token.is_expired(context):
            raise exceptions.JSONWebTokenError(_('Refresh token is expired'))

        payload = settings.jwt_settings.JWT_PAYLOAD_HANDLER(
            old_refresh_token.user,
            context,
        )
        token = settings.jwt_settings.JWT_ENCODE_HANDLER(payload, context)

        if getattr(context, 'jwt_cookie', False):
            context.jwt_refresh_token = create_refresh_token(
                old_refresh_token.user,
                old_refresh_token,
            )
            new_refresh_token = context.jwt_refresh_token.get_token()
        else:
            new_refresh_token = refresh_token_lazy(
                old_refresh_token.user,
                old_refresh_token,
            )

        refresh_signals.refresh_token_rotated.send(
            sender=RefreshMixin,
            request=context,
            refresh_token=old_refresh_token,
            refresh_token_issued=new_refresh_token,
        )
        return RefreshedTokenType(payload, token, new_refresh_token, refresh_expires_in=0)


if TYPE_CHECKING:
    base_class = BaseRefreshMixin
else:
    base_class = RefreshTokenMixin if settings.jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN else KeepAliveRefreshMixin


class RefreshMixin(base_class, JSONWebTokenMixin):
    """RefreshMixin"""
