from typing import Optional, cast

from django.http import HttpRequest, HttpResponse, JsonResponse
from strawberry.django.views import AsyncGraphQLView, BaseView, GraphQLView
from strawberry.http import GraphQLHTTPResponse, process_result
from strawberry.types import ExecutionResult

from strawberry_django_jwt.exceptions import JSONWebTokenError


class StatusGraphQLHTTPResponse(GraphQLHTTPResponse):
    status: Optional[int]


def make_status_response(response: GraphQLHTTPResponse) -> StatusGraphQLHTTPResponse:
    res = cast(StatusGraphQLHTTPResponse, response)
    res["status"] = 200
    return res


class BaseStatusHandlingGraphQLView(BaseView):
    def _create_response(
        self, response_data: GraphQLHTTPResponse, sub_response: HttpResponse
    ) -> JsonResponse:
        data = cast(StatusGraphQLHTTPResponse, response_data)
        response = JsonResponse(data, status=data.get("status", None))

        for name, value in sub_response.items():
            response[name] = value

        return response


class StatusHandlingGraphQLView(BaseStatusHandlingGraphQLView, GraphQLView):
    def process_result(
        self, request: HttpRequest, result: ExecutionResult
    ) -> StatusGraphQLHTTPResponse:
        res = make_status_response(process_result(result))
        if result.errors and any(
            isinstance(err, JSONWebTokenError) for err in [e.original_error for e in result.errors]
        ):
            res["status"] = 401
        return res


class AsyncStatusHandlingGraphQLView(BaseStatusHandlingGraphQLView, AsyncGraphQLView):
    async def process_result(
        self, request: HttpRequest, result: ExecutionResult
    ) -> StatusGraphQLHTTPResponse:
        res = make_status_response(process_result(result))
        if result.errors and any(
            isinstance(err, JSONWebTokenError) for err in [e.original_error for e in result.errors]
        ):
            res["status"] = 401
        return res
