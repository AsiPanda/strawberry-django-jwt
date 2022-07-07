import json

from django.contrib.auth import get_user_model
import strawberry
from strawberry.types import Info

from strawberry_django_jwt.decorators import login_required
from strawberry_django_jwt.middleware import (
    AsyncJSONWebTokenMiddleware,
    JSONWebTokenMiddleware,
)
from strawberry_django_jwt.mixins import JSONWebTokenMixin
from strawberry_django_jwt.settings import jwt_settings
from strawberry_django_jwt.shortcuts import get_token
from strawberry_django_jwt.testcases import AsyncJSONWebTokenClient, JSONWebTokenClient
from strawberry_django_jwt.views import (
    AsyncStatusHandlingGraphQLView,
    StatusHandlingGraphQLView,
)
from tests.testcases import AsyncSchemaTestCase, SchemaTestCase


class ViewClient(JSONWebTokenClient):
    def post(self, path, data, **kwargs):
        kwargs.setdefault("content_type", "application/json")
        return self.generic("POST", path, json.dumps(data), **kwargs)

    def execute(self, query, variables=None, **extra):
        self._setup_middleware()
        data = {
            "query": query,
            "variables": variables,
        }
        view = StatusHandlingGraphQLView(schema=self._schema)
        request = self.post("/", data=data, **extra)
        response = view.dispatch(request)
        content = self._parse_json(response)
        response.data = content.get("data")
        response.errors = content.get("errors")
        response.status_code = response.status_code
        return response


class ViewsTests(SchemaTestCase):
    client_class = ViewClient

    @strawberry.type
    class Query(JSONWebTokenMixin):
        @strawberry.field
        @login_required
        def test(self, info: Info) -> str:
            return "TEST"

    def setUp(self):
        super().setUp()

        self.other_user = get_user_model().objects.create_user("other")
        self.other_token = get_token(self.other_user)
        self.client.schema(query=ViewsTests.Query, mutation=self.Mutation)
        self.client.middleware([JSONWebTokenMiddleware])

    def test_login(self):
        query = """
        query Test {
            test
        }
        """

        headers = {
            jwt_settings.JWT_AUTH_HEADER_NAME: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {self.token}",
        }

        response = self.client.execute(query, **headers)
        data = response.data

        self.assertEqual(data["test"], "TEST")
        self.assertIsNone(response.errors)

    def test_invalid_credentials(self):
        query = """
        query Test {
            test
        }
        """

        response = self.client.execute(query)
        data = response.data

        self.assertIsNone(data)
        self.assertEqual(len(response.errors), 1)
        self.assertEqual(response.status_code, 401)

    def test_invalid_query(self):
        query = """
        query Test {
            invalidQuery
        }
        """

        response = self.client.execute(query)
        data = response.data

        self.assertIsNone(data)
        self.assertEqual(len(response.errors), 1)
        self.assertEqual(response.status_code, 200)


class AsyncViewClient(AsyncJSONWebTokenClient):
    def post(self, path, data, **kwargs):
        kwargs.setdefault("content_type", "application/json")
        return self.generic("POST", path, json.dumps(data), **kwargs)

    async def execute(self, query, variables=None, **extra):
        self._setup_middleware()
        data = {
            "query": query,
            "variables": variables,
        }
        view = AsyncStatusHandlingGraphQLView(schema=self._schema)
        request = self.post("/", data=data, **extra)
        response = await view.dispatch(request)
        content = self._parse_json(response)
        response.data = content.get("data")
        response.errors = content.get("errors")
        response.status_code = response.status_code
        return response


class AsyncViewsTests(AsyncSchemaTestCase):
    client_class = AsyncViewClient

    @strawberry.type
    class Query(JSONWebTokenMixin):
        @strawberry.field
        @login_required
        async def test(self, info: Info) -> str:
            return "TEST"

    def setUp(self):
        super().setUp()

        self.other_user = get_user_model().objects.create_user("other")
        self.other_token = get_token(self.other_user)
        self.client.schema(query=ViewsTests.Query, mutation=self.Mutation)
        self.client.middleware([AsyncJSONWebTokenMiddleware])

    async def test_login_async(self):
        query = """
        query Test {
            test
        }
        """

        headers = {
            jwt_settings.JWT_AUTH_HEADER_NAME.replace(
                "HTTP_", ""
            ): f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {self.token}",
        }

        response = await self.client.execute(query, **headers)
        data = response.data

        self.assertEqual(data["test"], "TEST")
        self.assertIsNone(response.errors)

    async def test_invalid_credentials_async(self):
        query = """
        query Test {
            test
        }
        """

        response = await self.client.execute(query)
        data = response.data

        self.assertIsNone(data)
        self.assertEqual(len(response.errors), 1)
        self.assertEqual(response.status_code, 401)

    async def test_invalid_query_async(self):
        query = """
        query Test {
            invalidQuery
        }
        """

        response = await self.client.execute(query)
        data = response.data

        self.assertIsNone(data)
        self.assertEqual(len(response.errors), 1)
        self.assertEqual(response.status_code, 200)
