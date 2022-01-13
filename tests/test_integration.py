from django.contrib.auth import get_user_model
from django.test.testcases import TestCase
from django.urls import reverse


class IntegrationTestCase(TestCase):
    login_query = """
    mutation TokenAuth($username: String!, $password: String!) {
      tokenAuth(username: $username, password: $password) {
        token
        payload {
            username
        }
      }
    }"""

    read_query = """
    query ReadQuery {
      value
    }"""

    @classmethod
    def setUpTestData(cls) -> None:
        get_user_model().objects.create_user(
            username="test",
            password="dolphins",
        )


class LoginTestCase(IntegrationTestCase):
    def test_login(self):
        data = {
            "query": self.login_query,
            "variables": {
                "username": "test",
                "password": "dolphins",
            },
        }
        response = self.client.post(
            reverse("sync_graphql"), data=data, content_type="application/json"
        )
        result = response.json()
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["data"]["tokenAuth"]["payload"], {"username": "test"})
        self.assertIsInstance(result["data"]["tokenAuth"]["token"], str)

    def test_read(self):
        data = {"query": self.read_query}
        response = self.client.post(
            reverse("sync_graphql"), data=data, content_type="application/json"
        )
        result = response.json()
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["data"]["value"], 1)

    async def test_login_asgi_request(self):
        """Test sync GraphQL View with an ASGIRequest"""
        data = {
            "query": self.login_query,
            "variables": {
                "username": "test",
                "password": "dolphins",
            },
        }
        response = await self.async_client.post(
            reverse("sync_graphql"), data=data, content_type="application/json"
        )
        result = response.json()
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["data"]["tokenAuth"]["payload"], {"username": "test"})
        self.assertIsInstance(result["data"]["tokenAuth"]["token"], str)

    async def test_read_asgi_request(self):
        """
        Test sync GraphQL View with an ASGIRequest

        Tests https://github.com/KundaPanda/strawberry-django-jwt/issues/194
        """
        data = {"query": self.read_query}
        response = await self.async_client.post(
            reverse("sync_graphql"), data=data, content_type="application/json"
        )
        result = response.json()
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["data"]["value"], 1)


class AsyncLoginTestCase(IntegrationTestCase):
    async def test_async_login(self):
        data = {
            "query": self.login_query,
            "variables": {
                "username": "test",
                "password": "dolphins",
            },
        }
        response = await self.async_client.post(
            reverse("graphql"), data=data, content_type="application/json"
        )
        result = response.json()
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["data"]["tokenAuth"]["payload"], {"username": "test"})
        self.assertIsInstance(result["data"]["tokenAuth"]["token"], str)

    async def test_async_read(self):
        data = {"query": self.read_query}
        response = await self.async_client.post(
            reverse("sync_graphql"), data=data, content_type="application/json"
        )
        result = response.json()
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["data"]["value"], 1)
