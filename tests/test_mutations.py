from importlib import reload
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django_mock_queries.query import MockModel, MockSet  # type: ignore
import strawberry.django
from strawberry.django import auto, mutations
from strawberry.types import Info

from strawberry_django_jwt.decorators import (
    dispose_extra_kwargs,
    login_field,
    login_required,
)
from strawberry_django_jwt.mixins import JSONWebTokenMixin
import strawberry_django_jwt.mutations
from strawberry_django_jwt.settings import jwt_settings
from strawberry_django_jwt.shortcuts import get_token
from tests.testcases import AsyncSchemaTestCase

from . import mixins
from .decorators import OverrideJwtSettings
from .models import MyTestModel
from .testcases import CookieTestCase, SchemaTestCase


class TokenAuthTests(mixins.TokenAuthMixin, SchemaTestCase):
    query = """
    mutation TokenAuth($username: String!, $password: String!) {
      tokenAuth(username: $username, password: $password) {
        token
        payload {
            username
        }
        refreshExpiresIn
      }
    }"""

    @strawberry.type
    class Mutation:
        token_auth = strawberry_django_jwt.mutations.ObtainJSONWebToken.obtain


class VerifyTests(mixins.VerifyMixin, SchemaTestCase):
    query = """
    mutation VerifyToken($token: String!) {
      verifyToken(token: $token) {
        payload {
            username
        }
      }
    }"""

    @strawberry.type
    class Mutation:
        verify_token = strawberry_django_jwt.mutations.Verify.verify


class RefreshTests(mixins.RefreshMixin, SchemaTestCase):
    query = """
    mutation RefreshToken($token: String) {
      refreshToken(token: $token) {
        token
        payload {
            username
            origIat
            exp
        }
        refreshExpiresIn
      }
    }"""

    @strawberry.type
    class Mutation:
        refresh_token = strawberry_django_jwt.mutations.Refresh.refresh

    @OverrideJwtSettings(JWT_HIDE_TOKEN_FIELDS=True)
    def test_hidden_token_fields(self):
        reload(strawberry_django_jwt.mixins)
        reload(strawberry_django_jwt.mutations)

        @strawberry.type
        class Mutation(JSONWebTokenMixin):
            @strawberry.field
            @dispose_extra_kwargs
            def test(self) -> str:
                return str(self)

        self.client.schema(query=self.Query, mutation=Mutation)

        query = """
        mutation RefreshToken($token: String) {
          test(token: $token)
        }"""

        token = get_token(self.user)
        response = self.client.execute(query, {"token": token})

        self.assertEqual(len(response.errors), 1)
        self.assertEqual(
            response.errors[0].message,
            "Unknown argument 'token' on field 'Mutation.test'.",
        )

    @OverrideJwtSettings(JWT_HIDE_TOKEN_FIELDS=False)
    def test_visible_token_fields(self):
        reload(strawberry_django_jwt.mixins)
        reload(strawberry_django_jwt.mutations)

        @strawberry.type
        class Mutation(JSONWebTokenMixin):
            @strawberry.field
            @dispose_extra_kwargs
            def test(self) -> str:
                return str(self)

        self.client.schema(query=self.Query, mutation=Mutation)

        query = """
        mutation RefreshToken($token: String) {
          test(token: $token)
        }"""

        token = get_token(self.user)
        response = self.client.execute(query, {"token": token})

        self.assertEqual(
            response.data.get("test").replace('"', "'"),
            json.dumps({"token": token}).replace('"', "'"),
        )


class CookieTokenAuthTests(mixins.CookieTokenAuthMixin, CookieTestCase):
    query = f"""
    mutation TokenAuth($username: String!, $password: String!) {{
      tokenAuth(username: $username, password: $password) {{
        token
        payload {{
            {get_user_model().USERNAME_FIELD}
        }}
        refreshExpiresIn
      }}
    }}"""

    @strawberry.type
    class Mutation:
        token_auth = strawberry_django_jwt.mutations.ObtainJSONWebToken.obtain

    def test_token_auth(self):
        return super().test_token_auth()

    def test_extended_field(self):
        @strawberry.type
        class Mutation:
            y: str = strawberry.field()

        self.query = """
        mutation TokenAuth {
          y
        }"""
        self.client.schema(query=self.Query, mutation=Mutation)
        response = self.execute()

        # Invalid mutation, only testing if ExtendedStrawberryField can handle fields without base_resolver
        self.assertEqual(len(response.errors), 1)


class CookieRefreshTests(mixins.CookieRefreshMixin, CookieTestCase):
    query = f"""
    mutation {{
      refreshToken {{
        token
        payload {{
            {get_user_model().USERNAME_FIELD}
        }}
        refreshExpiresIn
      }}
    }}"""

    @strawberry.type
    class Mutation:
        refresh_token = strawberry_django_jwt.mutations.Refresh.refresh


class DeleteCookieTests(mixins.DeleteCookieMixin, CookieTestCase):
    query = """
    mutation {
      deleteCookie {
        deleted
      }
    }"""

    @strawberry.type
    class Mutation:
        delete_cookie = strawberry_django_jwt.mutations.DeleteJSONWebTokenCookie.delete_cookie


class LoginLogoutTest(SchemaTestCase):
    login_query = """
    mutation TokenAuth($username: String!, $password: String!) {
      tokenAuth(username: $username, password: $password) {
        token
        payload {
            username
        }
      }
    }"""
    verify_query = """
    mutation VerifyToken($token: String!) {
      verifyToken(token: $token) {
        payload {
            username
        }
      }
    }"""
    mutate_query = """
    mutation Mutate {
      mutate
    }"""

    @strawberry.type
    class Mutation:
        token_auth = strawberry_django_jwt.mutations.ObtainJSONWebToken.obtain
        verify_token = strawberry_django_jwt.mutations.Verify.verify

        @login_field
        def mutate(self, info: Info) -> str:
            return "OK"

    def test_invalid_credentials(self):
        # Login
        self.query = self.login_query
        response = self.execute(
            {
                self.user.USERNAME_FIELD: self.user.get_username(),
                "password": "wrongpassword",
            }
        )
        self.assertIsNone(response.data)
        self.assertEqual(len(response.errors), 1)

    @OverrideJwtSettings(JWT_ALLOW_ARGUMENT=True)
    def test_login_logout(self):
        # Login
        self.query = self.login_query
        response = self.execute(
            {
                self.user.USERNAME_FIELD: self.user.get_username(),
                "password": "dolphins",
            }
        )

        self.assertIsNone(response.errors)
        self.assertEqual(
            response.data["tokenAuth"]["payload"]["username"], self.user.get_username()
        )
        token = response.data["tokenAuth"]["token"]

        # Verify with headers

        self.query = self.verify_query
        self.client.authenticate(token)
        response = self.execute({"token": token})

        self.assertIsNone(response.errors)
        self.assertEqual(
            response.data["verifyToken"]["payload"]["username"],
            self.user.get_username(),
        )

        # Check login

        self.query = self.mutate_query
        self.client.authenticate(token)
        response = self.execute()

        self.assertIsNone(response.errors)
        self.assertEqual(response.data["mutate"], "OK")

        # Logout

        self.query = self.mutate_query
        self.client.logout()
        response = self.execute()

        self.assertIsNone(response.data)
        self.assertEqual(len(response.errors), 1)


@strawberry.django.type(MyTestModel)
class MyTestType:
    test: auto


@strawberry.django.input(MyTestModel)
class MyTestInput:
    test: auto


class MutationFieldTests(SchemaTestCase):
    query = """
    mutation testCreate {
      testCreate(data: {test: "test"}) {
        test
      }
    }"""

    qs = MockSet(model=MyTestModel)
    objects = mock.patch("tests.models.MyTestModel.objects", qs)

    @strawberry.type
    class Mutation:
        test_create: MyTestType = login_required(mutations.create(MyTestInput))

    @objects
    def test_create_field_unauthorized(self):
        self.qs.add(MockModel(name="test"))

        response = self.execute()

        self.assertIs(len(response.errors), 1)
        self.assertIsNone(response.data)

    @objects
    def test_create_field(self):
        self.qs.add(MockModel(test="test123"))

        self.client.credentials(
            **{
                jwt_settings.JWT_AUTH_HEADER_NAME: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {self.token}",
            }
        )

        response = self.client.execute(self.query)

        data = response.data.get("testCreate")

        self.assertIsNone(response.errors)
        self.assertEqual(data["test"], "test")


class AsyncLoginLogoutTest(AsyncSchemaTestCase):
    login_query = """
    mutation TokenAuth($username: String!, $password: String!) {
      tokenAuth(username: $username, password: $password) {
        token
        payload {
            username
        }
      }
    }"""
    verify_query = """
    mutation VerifyToken($token: String!) {
      verifyToken(token: $token) {
        payload {
            username
        }
      }
    }"""
    mutate_query = """
    mutation Mutate {
      mutate
    }"""

    @strawberry.type
    class Mutation:
        token_auth = strawberry_django_jwt.mutations.ObtainJSONWebToken.obtain
        verify_token = strawberry_django_jwt.mutations.Verify.verify

        @login_field
        def mutate(self, info: Info) -> str:
            return "OK"

    async def test_invalid_credentials_async(self):
        # Login
        self.query = self.login_query
        response = await self.execute(
            {
                self.user.USERNAME_FIELD: self.user.get_username(),
                "password": "wrongpassword",
            }
        )
        self.assertIsNone(response.data)
        self.assertEqual(len(response.errors), 1)

    async def test_login_logout_async(self):
        self.client.schema(query=self.Query, mutation=self.Mutation)
        # Login
        self.query = self.login_query
        response = await self.execute(
            {
                self.user.USERNAME_FIELD: self.user.get_username(),
                "password": "dolphins",
            }
        )

        self.assertIsNone(response.errors)
        self.assertEqual(
            response.data["tokenAuth"]["payload"]["username"],
            self.user.get_username(),
        )
        token = response.data["tokenAuth"]["token"]

        # Verify with headers

        self.query = self.verify_query
        self.client.authenticate(token)
        response = await self.execute({"token": token})

        self.assertIsNone(response.errors)
        self.assertEqual(
            response.data["verifyToken"]["payload"]["username"],
            self.user.get_username(),
        )

        # Check login

        self.query = self.mutate_query
        self.client.authenticate(token)
        response = await self.execute()

        self.assertIsNone(response.errors)
        self.assertEqual(response.data["mutate"], "OK")

        # Logout

        self.query = self.mutate_query
        self.client.logout()
        response = await self.execute()

        self.assertIsNone(response.data)
        self.assertEqual(len(response.errors), 1)
