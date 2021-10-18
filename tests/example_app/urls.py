from django.contrib.auth.models import User
from django.urls import path, include
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated


# Serializers define the API representation.
from rest_framework.routers import DefaultRouter


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
    path("users", include(router.urls)),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
]
