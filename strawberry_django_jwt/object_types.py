from typing import Any, Dict, Tuple, Type, TypeVar

from django.contrib.auth import get_user_model
import strawberry.django

from strawberry_django_jwt.settings import jwt_settings

X = TypeVar("X", Any, Any)


def inject_fields(fields: Dict[str, Tuple[Type[X], X]]):
    def inject(cls):
        for field, data in fields.items():
            setattr(cls, field, data[1])
            cls.__annotations__[field] = data[0]
        return cls

    return inject


@strawberry.type
class DeleteType:
    deleted: bool


@strawberry.type
@inject_fields(
    {
        **{get_user_model().USERNAME_FIELD: (str, "")},
        **({"origIat": (int, 0)} if jwt_settings.JWT_ALLOW_REFRESH else {}),
        **({"aud": (str, "")} if jwt_settings.JWT_AUDIENCE else {}),
        **({"iss": (str, "")} if jwt_settings.JWT_ISSUER else {}),
    }
)
class TokenPayloadType:
    exp: int = 0
    origIat: int = 0


@strawberry.type
class PayloadType:
    payload: TokenPayloadType


@strawberry.type
@inject_fields(
    {
        **({"refresh_token": (str, "")} if jwt_settings.JWT_ALLOW_REFRESH else {}),
    }
)
class TokenDataType:
    payload: TokenPayloadType
    token: str = ""
    refresh_expires_in: int = 0
