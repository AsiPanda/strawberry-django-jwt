import asyncio
from typing import AsyncGenerator, List

import strawberry
from strawberry import Schema
from strawberry.types import Info

from strawberry_django_jwt.decorators import login_required
from strawberry_django_jwt.middleware import (
    AsyncJSONWebTokenMiddleware,
    JSONWebTokenMiddleware,
)
import strawberry_django_jwt.mutations as jwt_mutations


@strawberry.type
class Query:
    @strawberry.field
    @login_required
    async def week_days(self) -> List[str]:
        return [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

    @strawberry.field
    def value(self) -> int:
        return 1


@strawberry.type
class Subscription:
    @strawberry.subscription
    @login_required
    async def count(self, info: Info, target: int = 5) -> AsyncGenerator[int, None]:
        for i in range(target):
            yield i
            await asyncio.sleep(0.2)


@strawberry.type
class Mutation:
    token_auth = jwt_mutations.ObtainJSONWebToken.obtain
    verify_token = jwt_mutations.Verify.verify
    refresh_token = jwt_mutations.Refresh.refresh
    delete_cookie = jwt_mutations.DeleteJSONWebTokenCookie.delete_cookie


@strawberry.type
class MutationAsync:
    token_auth = jwt_mutations.ObtainJSONWebTokenAsync.obtain
    verify_token = jwt_mutations.VerifyAsync.verify
    refresh_token = jwt_mutations.RefreshAsync.refresh
    delete_cookie = jwt_mutations.DeleteJSONWebTokenCookieAsync.delete_cookie


schema = Schema(query=Query, mutation=MutationAsync, subscription=Subscription, extensions={AsyncJSONWebTokenMiddleware})
sync_schema = Schema(query=Query, mutation=Mutation, extensions=[JSONWebTokenMiddleware])
