from channels.testing import ChannelsLiveServerTestCase
from gql import gql
from gql.client import Client
from gql.transport.exceptions import TransportQueryError
from gql.transport.websockets import WebsocketsTransport
from testcases import AsyncUserTestCase

from strawberry_django_jwt.utils import jwt_encode, jwt_payload


class ChannelsTestCase(ChannelsLiveServerTestCase, AsyncUserTestCase):
    serve_static = False
    gql_subscription = gql(
        """
    subscription MySubscription {
        count(target: 3)
    }
"""
    )

    def setUp(self) -> None:
        super().setUp()
        self.payload = jwt_payload(self.user)
        self.token = jwt_encode(self.payload)
        headers = {"Authorization": "JWT " + self.token}
        self.unverified_ws_transport = WebsocketsTransport(url=self.live_server_ws_url + "/graphql", keep_alive_timeout=1000)
        self.unverified_ws_client = Client(transport=self.unverified_ws_transport, fetch_schema_from_transport=False)
        self.verified_ws_transport = WebsocketsTransport(url=self.live_server_ws_url + "/graphql", keep_alive_timeout=1000, headers=headers)
        self.verified_ws_client = Client(
            transport=self.verified_ws_transport,
            fetch_schema_from_transport=False,
        )

    # ---------------- tests -----------------
    async def execute_test(self, client: Client):
        index = 0
        async for res in self.unverified_ws_client.subscribe_async(self.gql_subscription):
            assert res["count"] == index
            index += 1

    async def test_not_authenticate_fails(self):
        try:
            await self.execute_test(self.unverified_ws_client)

        except TransportQueryError as exc:
            assert "'GraphQLWSConsumer' object has no attribute 'user'" in exc.errors[0]["message"]

    async def test_authenticated_succeeds(self):
        await self.execute_test(self.verified_ws_client)
