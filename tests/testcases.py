import json
from unittest import mock

import django
import strawberry
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import testcases
from graphql.execution.execute import GraphQLResolveInfo
from strawberry.django.views import GraphQLView
from strawberry_django_jwt.decorators import jwt_cookie
from strawberry_django_jwt.settings import jwt_settings
from strawberry_django_jwt.testcases import JSONWebTokenClient
from strawberry_django_jwt.testcases import JSONWebTokenTestCase
from strawberry_django_jwt.utils import jwt_encode
from strawberry_django_jwt.utils import jwt_payload


class UserTestCase(testcases.TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='test',
            password='dolphins',
        )


class TestCase(UserTestCase):

    def setUp(self):
        super().setUp()
        self.payload = jwt_payload(self.user)
        self.token = jwt_encode(self.payload)
        self.request_factory = RequestFactory()

    def info(self, user=None, **headers):
        request = self.request_factory.post('/', **headers)

        if user is not None:
            request.user = user

        return mock.Mock(
            context=request,
            path=['test'],
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
        assert self.query, ('`query` property not specified')
        return self.client.execute(self.query, variables)

    def assertUsernameIn(self, payload):
        username = payload[self.user.USERNAME_FIELD]
        self.assertEqual(self.user.get_username(), username)


class RelaySchemaTestCase(SchemaTestCase):

    def execute(self, variables=None):
        return super().execute({'input': variables})


class CookieClient(JSONWebTokenClient):

    def post(self, path, data, **kwargs):
        kwargs.setdefault('content_type', 'application/json')
        return self.generic('POST', path, json.dumps(data), **kwargs)

    def set_cookie(self, token):
        self.cookies[jwt_settings.JWT_COOKIE_NAME] = token

    def execute(self, query, variables=None, **extra):
        data = {
            'query': query,
            'variables': variables,
        }
        view = GraphQLView(schema=self._schema)
        request = self.post('/', data=data, **extra)
        response = jwt_cookie(view.dispatch)(request)
        content = self._parse_json(response)
        response.data = content.get('data')
        response.errors = content.get('errors')
        return response


class CookieTestCase(SchemaTestCase):
    client_class = CookieClient

    def set_cookie(self):
        self.client.set_cookie(self.token)


class RelayCookieTestCase(RelaySchemaTestCase, CookieTestCase):
    """RelayCookieTestCase"""


if django.VERSION[:2] >= (3, 1):
    from django.test import AsyncRequestFactory  # type: ignore
    from strawberry_django_jwt.testcases import AsyncJSONWebTokenTestCase


    class AsyncUserTestCase(testcases.TransactionTestCase, ):

        def setUp(self):
            self.user = get_user_model().objects.create_user(
                username='test',
                password='dolphins',
            )


    class AsyncTestCase(AsyncUserTestCase):

        def setUp(self):
            super().setUp()
            self.payload = jwt_payload(self.user)
            self.token = jwt_encode(self.payload)
            self.request_factory = AsyncRequestFactory()

        def info(self, user=None, **headers):
            request = self.request_factory.post('/', **headers)

            if user is not None:
                request.user = user

            return mock.Mock(
                context=request,
                path=['test'],
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

        async def execute(self, variables=None):
            assert self.query, ('`query` property not specified')
            return await self.client.execute(self.query, variables)

        def assertUsernameIn(self, payload):
            username = payload[self.user.USERNAME_FIELD]
            self.assertEqual(self.user.get_username(), username)
