import django
import strawberry
from django.contrib.auth.models import AnonymousUser
from django.core.handlers.wsgi import WSGIRequest
from django.test import Client
from django.test import RequestFactory
from django.test import testcases

from .middleware import JSONWebTokenMiddleware
from .settings import jwt_settings
from .shortcuts import get_token


class SchemaRequestFactory(RequestFactory):

    def __init__(self, **defaults):
        super().__init__(**defaults)
        self._schema = strawberry.Schema
        self._middleware = [JSONWebTokenMiddleware]

    def schema(self, **kwargs):
        self._schema = strawberry.Schema(**kwargs)

    def middleware(self, middleware):
        self._middleware = middleware

    def _setup_middleware(self):
        self._schema.middleware = [m() for m in self._middleware]

    def execute(self, query, **options):
        self._setup_middleware()
        return self._schema.execute_sync(query, validate_queries=False, **options)


class JSONWebTokenClient(SchemaRequestFactory, Client):

    def __init__(self, **defaults):
        super().__init__(**defaults)
        self._credentials = {}

    def request(self, **request):
        request = WSGIRequest(self._base_environ(**request))
        request.user = AnonymousUser()
        return request

    def credentials(self, **kwargs):
        self._credentials = kwargs

    def execute(self, query, variables=None, **extra):
        self._setup_middleware()
        extra.update(self._credentials)
        context = self.post('/', **extra)

        return super().execute(
            query,
            context_value=context,
            variable_values=variables,
        )

    def authenticate(self, token):
        self._credentials = {
            jwt_settings.JWT_AUTH_HEADER_NAME:
                f'{jwt_settings.JWT_AUTH_HEADER_PREFIX} {token}',
        }

    def logout(self):
        self._credentials.pop(jwt_settings.JWT_AUTH_HEADER_NAME, None)


class JSONWebTokenTestCase(testcases.TestCase):
    client_class = JSONWebTokenClient


if django.VERSION[:2] >= (3, 1):
    from django.core.handlers.asgi import ASGIRequest
    from django.test import AsyncClient  # type: ignore
    from django.test import AsyncRequestFactory  # type: ignore
    from .middleware import AsyncJSONWebTokenMiddleware
    from django.test.client import FakePayload


    class AsyncSchemaRequestFactory(AsyncRequestFactory):

        def __init__(self, **defaults):
            super().__init__(**defaults)
            self._schema = strawberry.Schema
            self._middleware = [AsyncJSONWebTokenMiddleware]

        def schema(self, **kwargs):
            self._schema = strawberry.Schema(**kwargs)

        def middleware(self, middleware):
            self._middleware = middleware

        def _setup_middleware(self):
            self._schema.middleware = [m() for m in self._middleware]


    class AsyncJSONWebTokenClient(AsyncSchemaRequestFactory, AsyncClient):

        def __init__(self, **defaults):
            super().__init__(**defaults)
            self._credentials = {}

        def request(self, **request):
            if request.get("custom_headers"):
                request["headers"].extend(
                    [(h.lower().encode("ascii"), v.encode("latin1"))
                     for h, v in request.get("custom_headers").items()])
            for idx, header in enumerate(request["headers"]):
                if header[0] == b"content-length":
                    del request["headers"][idx]
            body_file = request.pop('_body_file')
            request["headers"].append((b"content-length", bytes(f"{len(body_file)}", "latin1")))
            request = ASGIRequest(self._base_environ(**request), body_file)
            request.user = AnonymousUser()
            return request

        def credentials(self, **kwargs):
            self._credentials = kwargs

        def authenticate(self, user):
            self._credentials = {
                jwt_settings.JWT_AUTH_HEADER_NAME:
                    f'{jwt_settings.JWT_AUTH_HEADER_PREFIX} {get_token(user)}',
            }

        def logout(self):
            self._credentials.pop(jwt_settings.JWT_AUTH_HEADER_NAME, None)


    class AsyncJSONWebTokenTestCase(testcases.TransactionTestCase):
        client_class = AsyncJSONWebTokenClient
