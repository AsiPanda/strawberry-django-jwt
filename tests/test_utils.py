from datetime import timedelta
from functools import wraps
import importlib
from importlib import reload
from types import ModuleType
from unittest import mock

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa

from strawberry_django_jwt import exceptions, utils
import strawberry_django_jwt.object_types
from strawberry_django_jwt.object_types import TokenPayloadType
from strawberry_django_jwt.settings import jwt_settings
from strawberry_django_jwt.shortcuts import get_user_by_token_async
from tests.decorators import OverrideJwtSettings
from tests.testcases import AsyncTestCase, TestCase


def reload_import(imp: ModuleType):
    def wrap(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            importlib.reload(imp)
            return fn(*args, **kwargs)

        return wrapper

    return wrap


class JWTPayloadTests(TestCase):
    @mock.patch(
        "django.contrib.auth.models.User.get_username",
        return_value=mock.Mock(pk="test"),
    )
    def test_foreign_key_pk(self, *args):
        payload = utils.jwt_payload(self.user)
        username = jwt_settings.JWT_PAYLOAD_GET_USERNAME_HANDLER(payload)

        self.assertEqual(username, "test")

    @OverrideJwtSettings(JWT_AUDIENCE="test")
    @reload_import(strawberry_django_jwt.utils.object_types)
    def test_audience(self):
        payload = utils.jwt_payload(self.user)
        self.assertEqual(payload.aud, "test")

    @OverrideJwtSettings(JWT_ISSUER="test")
    @reload_import(strawberry_django_jwt.utils.object_types)
    def test_issuer(self):
        payload = utils.jwt_payload(self.user)
        self.assertEqual(payload.iss, "test")


class AsymmetricAlgorithmsTests(TestCase):
    def test_rsa_jwt(self):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        public_key = private_key.public_key()
        payload = utils.jwt_payload(self.user)

        with OverrideJwtSettings(
            JWT_PUBLIC_KEY=public_key,
            JWT_PRIVATE_KEY=private_key,
            JWT_ALGORITHM="RS256",
        ):
            token = utils.jwt_encode(payload)
            decoded = utils.jwt_decode(token)

        self.assertEqual(payload, decoded)


class GetHTTPAuthorizationHeaderTests(TestCase):
    def test_get_authorization_header(self):
        headers = {
            jwt_settings.JWT_AUTH_HEADER_NAME: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {self.token}",
        }

        request = self.request_factory.get("/", **headers)
        authorization_header = utils.get_http_authorization(request)

        self.assertEqual(authorization_header, self.token)

    def test_invalid_header_prefix(self):
        headers = {
            jwt_settings.JWT_AUTH_HEADER_NAME: "INVALID token",
        }

        request = self.request_factory.get("/", **headers)
        authorization_header = utils.get_http_authorization(request)

        self.assertIsNone(authorization_header)

    def test_get_authorization_cookie(self):
        headers = {
            jwt_settings.JWT_AUTH_HEADER_NAME: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {self.token}",
        }

        request = self.request_factory.get("/", **headers)
        request.COOKIES[jwt_settings.JWT_COOKIE_NAME] = self.token
        authorization_cookie = utils.get_http_authorization(request)

        self.assertEqual(authorization_cookie, self.token)


class GetCredentialsTests(TestCase):
    @OverrideJwtSettings(JWT_ALLOW_ARGUMENT=True)
    def test_argument_allowed(self):
        kwargs = {
            jwt_settings.JWT_ARGUMENT_NAME: self.token,
        }

        request = self.request_factory.get("/")
        credentials = utils.get_credentials(request, **kwargs)

        self.assertEqual(credentials, self.token)

    @OverrideJwtSettings(JWT_ALLOW_ARGUMENT=True)
    def test_input_argument(self):
        kwargs = {
            "input": {
                jwt_settings.JWT_ARGUMENT_NAME: self.token,
            },
        }

        request = self.request_factory.get("/")
        credentials = utils.get_credentials(request, **kwargs)

        self.assertEqual(credentials, self.token)

    @OverrideJwtSettings(JWT_ALLOW_ARGUMENT=True)
    def test_missing_argument(self):
        request = self.request_factory.get("/")
        credentials = utils.get_credentials(request)

        self.assertIsNone(credentials)


class GetPayloadTests(TestCase):
    @OverrideJwtSettings(JWT_VERIFY_EXPIRATION=True, JWT_EXPIRATION_DELTA=timedelta(seconds=-1))
    def test_expired_signature(self):
        payload = utils.jwt_payload(self.user)
        token = utils.jwt_encode(payload)

        with self.assertRaises(exceptions.JSONWebTokenExpired):
            utils.get_payload(token)

    def test_decode_audience_missing(self):
        payload = utils.jwt_payload(self.user)
        token = utils.jwt_encode(payload)

        with OverrideJwtSettings(JWT_AUDIENCE="test"), self.assertRaises(exceptions.JSONWebTokenError):
            utils.get_payload(token)

    def test_decode_error(self):
        with self.assertRaises(exceptions.JSONWebTokenError):
            utils.get_payload("invalid")


class GetUserByNaturalKeyTests(TestCase):
    def test_user_does_not_exists(self):
        user = utils.get_user_by_natural_key(0)
        self.assertIsNone(user)


class GetUserByPayloadTests(TestCase):
    def test_user_by_invalid_payload(self):
        with self.assertRaises(exceptions.JSONWebTokenError):
            utils.get_user_by_payload(TokenPayloadType())

    @mock.patch(
        "django.contrib.auth.models.User.is_active",
        new_callable=mock.PropertyMock,
        return_value=False,
    )
    def test_user_disabled_by_payload(self, *args):
        payload = utils.jwt_payload(self.user)

        with self.assertRaises(exceptions.JSONWebTokenError):
            utils.get_user_by_payload(payload)


class GetUserByNaturalKeyTestsAsync(AsyncTestCase):
    async def test_user_does_not_exists_async(self):
        user = await utils.get_user_by_natural_key_async(0)
        self.assertIsNone(user)


class GetUserByPayloadTestsAsync(AsyncTestCase):
    async def test_user_by_invalid_payload_async(self):
        with self.assertRaises(exceptions.JSONWebTokenError):
            await utils.get_user_by_payload_async(TokenPayloadType())

    async def test_user_disabled_by_payload_async(self):
        payload = utils.jwt_payload(self.user)

        with mock.patch(
            "django.contrib.auth.models.User.is_active",
            new_callable=mock.PropertyMock,
            return_value=False,
        ), self.assertRaises(exceptions.JSONWebTokenError):
            await utils.get_user_by_payload_async(payload)


class CreateUserTokenTestsAsync(AsyncTestCase):
    @OverrideJwtSettings(JWT_LONG_RUNNING_REFRESH_TOKEN=False)
    async def test_create_user_token_async(self):
        reload(utils)
        token = await utils.create_user_token(self.user)
        user = await get_user_by_token_async(token.token)
        assert user == self.user
        assert token.refresh_token is None
        assert token.refresh_expires_in - jwt_settings.JWT_EXPIRATION_DELTA.total_seconds() < 5

    @OverrideJwtSettings(JWT_LONG_RUNNING_REFRESH_TOKEN=True)
    async def test_create_user_token_with_refresh_async(self):
        token = await utils.create_user_token(self.user)
        user = await get_user_by_token_async(token.token)
        assert user == self.user
        assert token.refresh_token is not None
        assert token.refresh_expires_in - jwt_settings.JWT_REFRESH_EXPIRATION_DELTA.total_seconds() < 5
