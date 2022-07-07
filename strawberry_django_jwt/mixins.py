import inspect
from typing import Any, Dict, Optional

from django.utils.translation import gettext as _
import strawberry
from strawberry.field import StrawberryField
from strawberry.types import Info
from strawberry_django.fields.field import StrawberryDjangoField

from . import exceptions, settings
from .decorators import (
    csrf_rotation,
    ensure_token,
    refresh_expiration,
    setup_jwt_cookie,
)
from .fields import StrawberryDjangoRefreshTokenField, StrawberryDjangoTokenField
from .object_types import TokenDataType
from .refresh_token import signals as refresh_signals
from .refresh_token.decorators import ensure_refresh_token
from .refresh_token.object_types import RefreshedTokenType
from .refresh_token.shortcuts import (
    create_refresh_token,
    get_refresh_token,
    refresh_token_lazy,
)
from .signals import token_refreshed
from .utils import (
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
                field.arguments.append(
                    create_strawberry_argument(
                        "token", "token", str, **field_options.get("token", {})
                    )
                )
                if settings.jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN:
                    field.arguments.append(
                        create_strawberry_argument(
                            "refresh_token",
                            "refresh_token",
                            str,
                            **field_options.get("refresh_token", {}),
                        )
                    )


class JSONWebTokenMixin(BaseJSONWebTokenMixin):
    def __init_subclass__(cls, **kwargs):
        cls.init_fields(
            cls,
            {"token": {"is_optional": True}, "refresh_token": {"is_optional": True}},
        )


class KeepAliveRefreshMixin(JSONWebTokenMixin):
    @strawberry.mutation
    @setup_jwt_cookie
    @csrf_rotation
    @ensure_token
    def refresh(self, info: Info, token: Optional[str]) -> TokenDataType:
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
        refresh_expires_in = (
            orig_iat + settings.jwt_settings.JWT_REFRESH_EXPIRATION_DELTA.total_seconds()
        )

        token = settings.jwt_settings.JWT_ENCODE_HANDLER(payload, context) or ""
        token_refreshed.send(sender=RefreshMixin, request=context, user=user)

        result = TokenDataType(payload, token, refresh_expires_in)
        return maybe_thenable((result, token), on_resolve)


class RefreshTokenMixin(JSONWebTokenMixin):
    @strawberry.mutation
    @setup_jwt_cookie
    @csrf_rotation
    @refresh_expiration
    @ensure_refresh_token
    def refresh(self, info: Info, refresh_token: Optional[str]) -> RefreshedTokenType:
        context = get_context(info)
        old_refresh_token = get_refresh_token(refresh_token, context)

        if old_refresh_token.is_expired(context):
            raise exceptions.JSONWebTokenError(_("Refresh token is expired"))

        payload = settings.jwt_settings.JWT_PAYLOAD_HANDLER(
            old_refresh_token.user,
            context,
        )
        token = settings.jwt_settings.JWT_ENCODE_HANDLER(payload, context)

        if getattr(context, "jwt_cookie", False):
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


base_class = (
    RefreshTokenMixin
    if settings.jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN
    else KeepAliveRefreshMixin
)


class RefreshMixin(base_class, JSONWebTokenMixin):  # type: ignore
    """RefreshMixin."""
