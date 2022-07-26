import inspect
from typing import Any, Dict, Optional, Type, Union

from asgiref.sync import sync_to_async
from django.utils.translation import gettext as _
import strawberry
from strawberry.field import StrawberryField
from strawberry.types import Info
from strawberry_django.fields.field import StrawberryDjangoField

from strawberry_django_jwt import exceptions, settings
from strawberry_django_jwt.decorators import (
    csrf_rotation,
    ensure_token,
    refresh_expiration,
    setup_jwt_cookie,
)
from strawberry_django_jwt.fields import (
    StrawberryDjangoRefreshTokenField,
    StrawberryDjangoTokenField,
)
from strawberry_django_jwt.object_types import TokenDataType
from strawberry_django_jwt.refresh_token import signals as refresh_signals
from strawberry_django_jwt.refresh_token.decorators import ensure_refresh_token
from strawberry_django_jwt.refresh_token.object_types import RefreshedTokenType
from strawberry_django_jwt.refresh_token.shortcuts import (
    create_refresh_token,
    get_refresh_token,
    refresh_token_lazy,
)
from strawberry_django_jwt.signals import token_refreshed
from strawberry_django_jwt.utils import (
    create_strawberry_argument,
    get_context,
    get_payload,
    get_user_by_payload,
    maybe_thenable,
)


class BaseJSONWebTokenMixin:
    @staticmethod
    def init_fields(cls, field_options: Dict[str, Dict[str, Any]]):
        if not settings.jwt_settings.JWT_HIDE_TOKEN_FIELDS:
            for (__, field) in inspect.getmembers(cls, lambda f: isinstance(f, StrawberryField)):
                if field.type_annotation is None and isinstance(field, StrawberryDjangoField):
                    # StrawberryDjangoFields resolve their arguments after strawberry decorator is applied.
                    # It is necessary to add subclasses to the field class which provide required arguments when
                    #   fields are collected.
                    base_types = StrawberryDjangoField, StrawberryDjangoTokenField
                    if settings.jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN:
                        new_type = type(
                            "StrawberryDjangoJWTField",
                            (
                                *base_types,
                                StrawberryDjangoRefreshTokenField,
                            ),
                            {},
                        )
                    else:
                        new_type = type("StrawberryDjangoJWTField", base_types, {})
                    field.__class__ = new_type
                    continue
                field.arguments.append(create_strawberry_argument("token", "token", str, **field_options.get("token", {})))
                if settings.jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN:
                    field.arguments.append(create_strawberry_argument("refresh_token", "refreshToken", str, **field_options.get("refresh_token", {})))


class JSONWebTokenMixin(BaseJSONWebTokenMixin):
    def __init_subclass__(cls, **kwargs):
        cls.init_fields(
            cls,
            {"token": {"is_optional": True}, "refresh_token": {"is_optional": True}},
        )


class KeepAliveRefreshMixin(JSONWebTokenMixin):
    @staticmethod
    @setup_jwt_cookie
    @csrf_rotation
    @ensure_token
    def _refresh(self, info: Info, token: Optional[str]) -> TokenDataType:
        def on_resolve(values):
            payload, token = values
            payload.token = token
            return payload

        context = get_context(info)
        payload = get_payload(token, context)
        user = get_user_by_payload(payload)
        orig_iat = payload.origIat

        if orig_iat is None:
            raise exceptions.JSONWebTokenError(_("origIat field is required"))

        if settings.jwt_settings.JWT_REFRESH_EXPIRED_HANDLER(orig_iat, context):
            raise exceptions.JSONWebTokenError(_("Refresh has expired"))

        payload = settings.jwt_settings.JWT_PAYLOAD_HANDLER(user, context)
        payload.origIat = orig_iat
        refresh_expires_in = orig_iat + settings.jwt_settings.JWT_REFRESH_EXPIRATION_DELTA.total_seconds()

        token = settings.jwt_settings.JWT_ENCODE_HANDLER(payload, context) or ""
        token_refreshed.send(sender=RefreshMixin, request=context, user=user)

        result = TokenDataType(payload, token, refresh_expires_in)
        return maybe_thenable((result, token), on_resolve)

    def refresh(self, info: Info, token: Optional[str] = None) -> TokenDataType:
        return KeepAliveRefreshMixin._refresh(self, info=info, token=token)

    async def refresh_async(self, info: Info, token: Optional[str] = None) -> TokenDataType:
        return await sync_to_async(KeepAliveRefreshMixin._refresh)(self, info=info, token=token)


class RefreshTokenMixin(JSONWebTokenMixin):
    @staticmethod
    @setup_jwt_cookie
    @csrf_rotation
    @refresh_expiration
    @ensure_refresh_token
    def _refresh(self, info: Info, refresh_token: Optional[str]) -> RefreshedTokenType:
        context = get_context(info)
        old_refresh_token = get_refresh_token(refresh_token, context)

        if old_refresh_token.is_expired(context):
            raise exceptions.JSONWebTokenError(_("Refresh token is expired"))

        payload = settings.jwt_settings.JWT_PAYLOAD_HANDLER(
            old_refresh_token.user,
            context,
        )
        token = settings.jwt_settings.JWT_ENCODE_HANDLER(payload, context)

        if hasattr(context, "jwt_cookie"):
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

    def refresh(self, info: Info, refresh_token: Optional[str] = None) -> RefreshedTokenType:
        return RefreshTokenMixin._refresh(self, info=info, refresh_token=refresh_token)

    async def refresh_async(self, info: Info, refresh_token: Optional[str] = None) -> RefreshedTokenType:
        return await sync_to_async(RefreshTokenMixin._refresh)(self, info=info, refresh_token=refresh_token)


base_class: Type[Union[RefreshTokenMixin, KeepAliveRefreshMixin]] = (
    RefreshTokenMixin if settings.jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN else KeepAliveRefreshMixin
)


class RefreshMixin(base_class, JSONWebTokenMixin):  # type: ignore
    """RefreshMixin"""

    refresh = strawberry.mutation(base_class.refresh)


class AsyncRefreshMixin(base_class, JSONWebTokenMixin):  # type: ignore
    """Async version of RefreshMixin"""

    refresh = strawberry.mutation(base_class.refresh_async)
