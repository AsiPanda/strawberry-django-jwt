import base64

import django
import pytest
from django.contrib.auth.models import User
from django.test import Client, TestCase as DjangoTestCase
from rest_framework.test import APIClient

from strawberry_django_jwt.backends import JSONWebTokenBackend
from strawberry_django_jwt.exceptions import JSONWebTokenError
from strawberry_django_jwt.settings import jwt_settings
from .testcases import AsyncTestCase, TestCase


@pytest.mark.django_db
class MultipleBackendsTests(DjangoTestCase):
    django_client: Client
    djrf_client: APIClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.django_client = Client()
        cls.djrf_client = APIClient()
        super().setUpClass()

    def test_djrf_backend(self):
        response = self.djrf_client.get("/users")
        assert response.status_code == 401

    def test_djrf_backend_authenticated(self):
        User.objects.create_user(
            username="test", password="test_pass", email="test@test.test"
        )
        self.djrf_client.credentials(
            HTTP_AUTHORIZATION=f'Basic {base64.b64encode(b"test:test_pass").decode()}'
        )
        response = self.djrf_client.get("/users")
        assert response.status_code == 200


class BackendsTests(TestCase):
    def setUp(self):
        super().setUp()
        self.backend = JSONWebTokenBackend()

    def test_authenticate(self):
        headers = {
            jwt_settings.JWT_AUTH_HEADER_NAME: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {self.token}",
        }

        request = self.request_factory.get("/", **headers)
        user = self.backend.authenticate(request=request)

        self.assertEqual(user, self.user)

    def test_authenticate_fail(self):
        headers = {
            jwt_settings.JWT_AUTH_HEADER_NAME: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} invalid",
        }

        request = self.request_factory.get("/", **headers)

        with self.assertRaises(JSONWebTokenError):
            self.backend.authenticate(request=request)

    def test_authenticate_null_request(self):
        user = self.backend.authenticate(request=None)
        self.assertIsNone(user)

    def test_authenticate_missing_token(self):
        request = self.request_factory.get("/")
        user = self.backend.authenticate(request=request)

        self.assertIsNone(user)

    def test_get_user(self):
        user = self.backend.get_user(self.user.pk)
        self.assertIsNone(user)


class AsyncBackendsTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.backend = JSONWebTokenBackend()

    async def test_authenticate_async(self):
        name = (
            jwt_settings.JWT_AUTH_HEADER_NAME
            if django.VERSION[:2] < (3, 2)
            else jwt_settings.JWT_AUTH_HEADER_NAME.replace("HTTP_", "")
        )
        headers = {
            name: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {self.token}",
        }

        request = self.request_factory.get("/", **headers)
        if django.VERSION[:2] == (3, 1):
            request.META.update(headers)
        user = await self.backend.authenticate_async(request=request)

        self.assertEqual(user, self.user)

    async def test_authenticate_fail_async(self):
        name = (
            jwt_settings.JWT_AUTH_HEADER_NAME
            if django.VERSION[:2] < (3, 2)
            else jwt_settings.JWT_AUTH_HEADER_NAME.replace("HTTP_", "")
        )
        headers = {
            name: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} invalid",
        }

        request = self.request_factory.get("/", **headers)
        if django.VERSION[:2] == (3, 1):
            request.META.update(headers)

        with self.assertRaises(JSONWebTokenError):
            await self.backend.authenticate_async(request=request)

    async def test_authenticate_null_request_async(self):
        user = await self.backend.authenticate_async(request=None)
        self.assertIsNone(user)

    async def test_authenticate_missing_token_async(self):
        request = self.request_factory.get("/")
        user = await self.backend.authenticate_async(request=request)

        self.assertIsNone(user)
