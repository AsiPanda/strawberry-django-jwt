import json
from unittest import mock

import strawberry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import AsyncRequestFactory, RequestFactory, testcases  # type: ignore
from graphql.execution.execute import GraphQLResolveInfo
from strawberry.django.views import AsyncGraphQLView, GraphQLView

from strawberry_django_jwt.decorators import jwt_cookie
from strawberry_django_jwt.settings import jwt_settings
from strawberry_django_jwt.testcases import (
    AsyncJSONWebTokenClient,
    AsyncJSONWebTokenTestCase,
    JSONWebTokenClient,
    JSONWebTokenTestCase,
)
from strawberry_django_jwt.utils import jwt_encode, jwt_payload
from tests.models import MyTestModel


class UserTestCase(testcases.TestCase):
    def setUp(self):
        self.user: User = get_user_model().objects.create_user(
            username="test",
            password="dolphins",
        )
        self.test_permission = Permission.objects.create(
            codename="run_tests",
            name="Can run tests",
            content_type=ContentType.objects.get_for_model(MyTestModel),
        )
        self.user.user_permissions.add(self.test_permission)


class TestCase(UserTestCase):
    def setUp(self):
        super().setUp()
        self.payload = jwt_payload(self.user)
        self.token = jwt_encode(self.payload)
        self.request_factory = RequestFactory()

    def info(self, user=None, **headers):
        request = self.request_factory.post("/", **headers)

        if user is not None:
            request.user = user

        return mock.Mock(
            context=request,
            path=["test"],
            spec=GraphQLResolveInfo,
        )


class SchemaTestCase(TestCase, JSONWebTokenTestCase):
    @strawberry.type
    class Query:
        test: str

    Mutation = None

    def setUp(self):
        super().setUp()
        self.client.schema(query=self.Query, mutation=self.Mutation)

    def execute(self, variables=None):
        assert self.query, "`query` property not specified"
        return self.client.execute(self.query, variables)

    def assertUsernameIn(self, payload):
        username = payload[self.user.USERNAME_FIELD]
        self.assertEqual(self.user.get_username(), username)


class RelaySchemaTestCase(SchemaTestCase):
    def execute(self, variables=None):
        return super().execute({"input": variables})


class CookieClient(JSONWebTokenClient):
    def post(self, path, data, **kwargs):
        kwargs.setdefault("content_type", "application/json")
        return self.generic("POST", path, json.dumps(data), **kwargs)

    def set_cookie(self, token):
        self.cookies[jwt_settings.JWT_COOKIE_NAME] = token

    def execute(self, query, variables=None, **extra):
        data = {
            "query": query,
            "variables": variables,
        }
        view = GraphQLView(schema=self._schema)
        request = self.post("/", data=data, **extra)
        response = jwt_cookie(view.dispatch)(request)
        content = self._parse_json(response)
        response.data = content.get("data")
        response.errors = content.get("errors")
        return response


class CookieTestCase(SchemaTestCase):
    client_class = CookieClient

    def set_cookie(self):
        self.client.set_cookie(self.token)


class RelayCookieTestCase(RelaySchemaTestCase, CookieTestCase):
    """RelayCookieTestCase"""


class AsyncUserTestCase(testcases.TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="test",
            password="dolphins",
        )


class AsyncTestCase(AsyncUserTestCase):
    def setUp(self):
        super().setUp()
        self.payload = jwt_payload(self.user)
        self.token = jwt_encode(self.payload)
        self.request_factory = AsyncRequestFactory()

    def info(self, user=None, **headers):
        request = self.request_factory.post("/", **headers)

        if user is not None:
            request.user = user

        return mock.Mock(
            context=request,
            path=["test"],
            spec=GraphQLResolveInfo,
        )


class AsyncSchemaTestCase(AsyncTestCase, AsyncJSONWebTokenTestCase):
    @strawberry.type
    class Query:
        test: str

    Mutation = None

    def setUp(self):
        super().setUp()
        self.client.schema(query=self.Query, mutation=self.Mutation)

    def execute(self, variables=None):
        assert self.query, "`query` property not specified"
        return self.client.execute(self.query, variables)

    def assertUsernameIn(self, payload):
        username = payload[self.user.USERNAME_FIELD]
        self.assertEqual(self.user.get_username(), username)


class AsyncCookieClient(AsyncJSONWebTokenClient):
    def post(self, path, data, **kwargs):
        kwargs.setdefault("content_type", "application/json")
        return self.generic("POST", path, json.dumps(data), **kwargs)

    def set_cookie(self, token):
        self.cookies[jwt_settings.JWT_COOKIE_NAME] = token

    async def execute(self, query, variables=None, **extra):
        data = {
            "query": query,
            "variables": variables,
        }
        view = AsyncGraphQLView(schema=self._schema)
        request = self.post("/", data=data, **extra)
        response = await jwt_cookie(view.dispatch)(request)
        content = self._parse_json(response)
        response.data = content.get("data")
        response.errors = content.get("errors")
        return response


class AsyncCookieTestCase(AsyncSchemaTestCase):
    client_class = AsyncCookieClient

    def set_cookie(self):
        self.client.set_cookie(self.token)
