from typing import List

import strawberry
from strawberry import Schema

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
class Mutation:
    token_auth = jwt_mutations.ObtainJSONWebToken.obtain
    verify_token = jwt_mutations.Verify.verify
    refresh_token = jwt_mutations.Refresh.refresh
    delete_cookie = jwt_mutations.DeleteJSONWebTokenCookie.delete_cookie


schema = Schema(query=Query, mutation=Mutation, extensions=[AsyncJSONWebTokenMiddleware])
sync_schema = Schema(query=Query, mutation=Mutation, extensions=[JSONWebTokenMiddleware])
