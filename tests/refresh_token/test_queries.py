from typing import List

import pytest
import strawberry
import strawberry_django

from strawberry_django_jwt.decorators import login_required
from strawberry_django_jwt.mixins import JSONWebTokenMixin
from strawberry_django_jwt.settings import jwt_settings
from tests.decorators import OverrideJwtSettings
from tests.strawberry_types import MyTestModel
from tests.testcases import SchemaTestCase


class QueriesTests(SchemaTestCase):
    @pytest.mark.django_db
    @OverrideJwtSettings(JWT_LONG_RUNNING_REFRESH_TOKEN=True)
    def test_strawberry_graphql_django_model_fields(self):
        @strawberry.type
        class Query(JSONWebTokenMixin):
            # test_model: List[MyTestModel] = strawberry_django.field()
            test_model: List[MyTestModel] = login_required(strawberry_django.field())

        self.client.schema(query=Query, mutation=self.Mutation)

        query = """
        query Test {
            testModel {
                test
            }
        }
        """

        headers = {
            jwt_settings.JWT_AUTH_HEADER_NAME: f"{jwt_settings.JWT_AUTH_HEADER_PREFIX} {self.token}",
        }

        response = self.client.execute(query, **headers)
        data = response.data

        self.assertEqual(data["testModel"], [])
        self.assertIsNone(response.errors)
