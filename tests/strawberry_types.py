from strawberry import auto
import strawberry_django

from tests import models


@strawberry_django.type(models.MyTestModel)
class MyTestModel:
    test: auto
