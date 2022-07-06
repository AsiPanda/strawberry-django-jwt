from django.contrib.auth.models import AnonymousUser
from django.core.handlers.asgi import ASGIRequest
from django.core.handlers.wsgi import WSGIRequest
from django.test import AsyncClient, Client, RequestFactory, testcases  # type: ignore
from django.test import AsyncRequestFactory  # type: ignore
import strawberry

from strawberry_django_jwt.middleware import (
    AsyncJSONWebTokenMiddleware,
    JSONWebTokenMiddleware,
)
from strawberry_django_jwt.settings import jwt_settings


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
        self._schema.extensions = list(self._middleware)

    def execute(self, query, **options):
        self._setup_middleware()
        return self._schema.execute_sync(query, **options)


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
        context = self.post("/", **extra)

        return super().execute(
            query,
            context_value=context,
            variable_values=variables,
        )

    def authenticate(self, token):
        self._credentials = {
            jwt_settings.JWT_AUTH_HEADER_NAME: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {token}",
        }

    def logout(self):
        self._credentials.pop(jwt_settings.JWT_AUTH_HEADER_NAME, None)


class JSONWebTokenTestCase(testcases.TestCase):
    client_class = JSONWebTokenClient


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
        self._schema.extensions = list(self._middleware)

    def execute(self, query, **options):
        self._setup_middleware()
        return self._schema.execute(query, **options)


class AsyncJSONWebTokenClient(AsyncSchemaRequestFactory, AsyncClient):
    def __init__(self, **defaults):
        super().__init__(**defaults)
        self._credentials = {}

    def request(self, **request):
        for idx, header in enumerate(request["headers"]):
            if header[0] == b"content-length":
                del request["headers"][idx]
        body_file = request.pop("_body_file")
        request["headers"].append((b"content-length", bytes(f"{len(body_file)}", "latin1")))
        request = ASGIRequest(self._base_environ(**request), body_file)
        request.user = AnonymousUser()
        return request

    def credentials(self, **kwargs):
        self._credentials = kwargs

    def execute(self, query, variables=None, **extra):
        context = self.post(query, **self._credentials, **extra)

        return super().execute(
            query,
            context_value=context,
            variable_values=variables,
        )

    def authenticate(self, token):
        self.credentials(
            **{
                jwt_settings.JWT_AUTH_HEADER_NAME.replace(
                    "HTTP_", ""
                ): f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {token}",
            }
        )

    def logout(self):
        self._credentials.pop(jwt_settings.JWT_AUTH_HEADER_NAME.replace("HTTP_", ""), None)


class AsyncJSONWebTokenTestCase(testcases.TransactionTestCase):
    client_class = AsyncJSONWebTokenClient
