from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from strawberry_django_jwt.auth import authenticate
from strawberry_django_jwt.backends import JSONWebTokenBackend
from tests.testcases import AsyncTestCase


class EmptyAuth:
    def authenticate(self):
        return None


class AsyncDefaultAuth:
    async def authenticate(self, request=None, **kwargs):
        return None


class SyncDefaultAuth:
    def authenticate(self, request=None, **kwargs):
        return None


class PermissionDeniedAuth:
    def authenticate(self, request=None, **kwargs):
        raise PermissionDenied()


class AsyncAuthTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.backend = JSONWebTokenBackend()
        self.old_backends = settings.AUTHENTICATION_BACKENDS[:]
        self.user = get_user_model().objects.create_user("someuser")

    def tearDown(self) -> None:
        settings.AUTHENTICATION_BACKENDS = self.old_backends[:]

    async def test_wsgi_authenticate(self):
        settings.AUTHENTICATION_BACKENDS = ["tests.test_auth.SyncDefaultAuth"]
        request = self.request_factory.post("/")

        def _authenticate(_=None, **__):
            return self.user

        with patch(
            "tests.test_auth.SyncDefaultAuth.authenticate",
            side_effect=_authenticate,
        ):
            result = await authenticate(request)

        self.assertEqual(result, self.user)

    async def test_permission_denied(self):
        settings.AUTHENTICATION_BACKENDS = ["tests.test_auth.PermissionDeniedAuth"]
        request = self.request_factory.post("/")

        result = await authenticate(request)

        self.assertIsNone(result)

    async def test_invalid_signature(self):
        settings.AUTHENTICATION_BACKENDS = ["tests.test_auth.EmptyAuth"]
        request = self.request_factory.post("/")

        result = await authenticate(request)

        self.assertIsNone(result)

    async def test_async_authenticate_signature(self):
        settings.AUTHENTICATION_BACKENDS = ["tests.test_auth.AsyncDefaultAuth"]
        request = self.request_factory.post("/")

        async def _authenticate(_=None, **__):
            return self.user

        with patch(
            "tests.test_auth.AsyncDefaultAuth.authenticate",
            side_effect=_authenticate,
        ):
            result = await authenticate(request)

        self.assertEqual(result, self.user)

    async def test_wsgi_authenticate_async(self):
        settings.AUTHENTICATION_BACKENDS = ["tests.test_auth.SyncDefaultAuth"]
        request = RequestFactory().post("/")

        with patch(
            "tests.test_auth.SyncDefaultAuth.authenticate",
            return_value=self.user,
        ):
            result = await authenticate(request)

        self.assertEqual(result, self.user)
