from django.contrib.auth.models import User
from django.urls import include, path, re_path
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

# Serializers define the API representation.
from rest_framework.routers import DefaultRouter

from strawberry_django_jwt.decorators import jwt_cookie
from tests.example_app.schema import schema, sync_schema
from strawberry_django_jwt.views import (
    AsyncStatusHandlingGraphQLView as AGQLView,
    StatusHandlingGraphQLView as GQLView,
)


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ["url", "username", "email", "is_staff"]


# ViewSets define the view behavior.
class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all()
    serializer_class = UserSerializer


router = DefaultRouter()
router.register(r"", UserViewSet, basename="user")

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    re_path(
        r"^graphql/?$", jwt_cookie(AGQLView.as_view(schema=schema)), name="graphql"
    ),
    re_path(
        r"^sync-graphql/?$",
        jwt_cookie(GQLView.as_view(schema=sync_schema)),
        name="sync_graphql",
    ),
    path("users", include(router.urls)),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
]
