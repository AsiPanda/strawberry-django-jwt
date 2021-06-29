import django
import strawberry

import strawberry_django_jwt.mutations
from . import mixins
from .mutations import Refresh
from .testcases import CookieTestCase
from ..testcases import SchemaTestCase


class TokenAuthTests(mixins.TokenAuthMixin, SchemaTestCase):
    query = """
    mutation TokenAuth($username: String!, $password: String!) {
      tokenAuth(username: $username, password: $password) {
        token
        payload {
            username
        }
        refreshToken
        refreshExpiresIn
      }
    }"""

    refresh_token_mutations = {
        "token_auth": strawberry_django_jwt.mutations.ObtainJSONWebToken.obtain,
    }


class RefreshTests(mixins.RefreshMixin, SchemaTestCase):
    query = """
    mutation RefreshToken($refreshToken: String) {
      refreshToken(refreshToken: $refreshToken) {
        token
        payload {
            username
            origIat
            exp
        }
        refreshToken
        refreshExpiresIn
      }
    }"""

    refresh_token_mutations = {
        "refresh_token": Refresh.refresh,
    }


class RevokeTests(mixins.RevokeMixin, SchemaTestCase):
    query = """
    mutation RevokeToken($refreshToken: String!) {
      revokeToken(refreshToken: $refreshToken) {
        revoked
      }
    }"""

    @strawberry.type
    class Mutation:
        revoke_token = strawberry_django_jwt.mutations.Revoke.revoke


class CookieTokenAuthTests(mixins.CookieTokenAuthMixin, CookieTestCase):
    query = """
    mutation TokenAuth($username: String!, $password: String!) {
      tokenAuth(username: $username, password: $password) {
        token
        payload {
            username
            origIat
        }
        refreshToken
        refreshExpiresIn
      }
    }"""

    refresh_token_mutations = {
        "token_auth": strawberry_django_jwt.mutations.ObtainJSONWebToken.obtain,
    }


class CookieRefreshTests(mixins.CookieRefreshMixin, CookieTestCase):
    query = """
    mutation {
      refreshToken {
        token
        payload {
          username
        }
        refreshToken
        refreshExpiresIn
      }
    }"""

    refresh_token_mutations = {
        "refresh_token": Refresh.refresh,
    }


class DeleteCookieTests(mixins.DeleteCookieMixin, CookieTestCase):
    query = """
    mutation {
      deleteCookie {
        deleted
      }
    }"""

    @strawberry.type
    class Mutation:
        delete_cookie = (
            strawberry_django_jwt.mutations.DeleteRefreshTokenCookie.delete_cookie
        )


if django.VERSION[:2] >= (3, 1):
    from .testcases import AsyncCookieTestCase
    from ..testcases import AsyncSchemaTestCase

    class AsyncCookieTokenAuthTests(
        mixins.AsyncCookieTokenAuthMixin, AsyncCookieTestCase
    ):
        query = """
        mutation TokenAuth($username: String!, $password: String!) {
          tokenAuth(username: $username, password: $password) {
            token
            payload {
                username
                origIat
            }
            refreshToken
            refreshExpiresIn
          }
        }"""

        refresh_token_mutations = {
            "token_auth": strawberry_django_jwt.mutations.ObtainJSONWebToken.obtain,
        }

    class AsyncTokenAuthTests(mixins.AsyncTokenAuthMixin, AsyncSchemaTestCase):
        query = """
        mutation TokenAuth($username: String!, $password: String!) {
          tokenAuth(username: $username, password: $password) {
            token
            payload {
                username
            }
            refreshToken
            refreshExpiresIn
          }
        }"""

        refresh_token_mutations = {
            "token_auth": strawberry_django_jwt.mutations.ObtainJSONWebToken.obtain,
        }
