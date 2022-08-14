"""
ASGI config for example_app project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path
from example_app.schema import schema
from strawberry.channels.handlers.http_handler import GraphQLHTTPConsumer
from strawberry.channels.handlers.ws_handler import GraphQLWSConsumer

django_asgi_app = get_asgi_application()


# http tests or any tests that are extended from Django's TestCase will run against WSGI anyway.
# so the http consumer is not really necessary.It is just for graphiql.


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.example_app.settings")


gql_http_consumer = AuthMiddlewareStack(GraphQLHTTPConsumer.as_asgi(schema=schema))
gql_ws_consumer = GraphQLWSConsumer.as_asgi(schema=schema)
application = ProtocolTypeRouter(
    {
        "http": URLRouter(
            [
                re_path("^graphql", gql_http_consumer),
                re_path("^", django_asgi_app),
            ]
        ),
        "websocket": AuthMiddlewareStack(gql_ws_consumer),
    }
)
