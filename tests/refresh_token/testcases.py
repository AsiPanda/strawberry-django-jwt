from strawberry_django_jwt.settings import jwt_settings
from strawberry_django_jwt.shortcuts import create_refresh_token
from tests import testcases


class CookieClient(testcases.CookieClient):
    def set_refresh_token_cookie(self, token):
        self.cookies[jwt_settings.JWT_REFRESH_TOKEN_COOKIE_NAME] = token


class CookieTestCase(testcases.CookieTestCase):
    client_class = CookieClient

    def setUp(self):
        super().setUp()
        self.refresh_token = create_refresh_token(self.user)

    def set_refresh_token_cookie(self):
        self.client.set_refresh_token_cookie(self.refresh_token.token)


class AsyncCookieClient(testcases.AsyncCookieClient):
    def set_refresh_token_cookie(self, token):
        self.cookies[jwt_settings.JWT_REFRESH_TOKEN_COOKIE_NAME] = token


class AsyncCookieTestCase(testcases.AsyncCookieTestCase):
    client_class = AsyncCookieClient

    def setUp(self):
        super().setUp()
        self.refresh_token = create_refresh_token(self.user)

    def set_refresh_token_cookie(self):
        self.client.set_refresh_token_cookie(self.refresh_token.token)
