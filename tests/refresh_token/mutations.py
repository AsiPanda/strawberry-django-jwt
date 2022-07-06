from strawberry_django_jwt.mixins import JSONWebTokenMixin, RefreshTokenMixin


class Refresh(RefreshTokenMixin, JSONWebTokenMixin):
    pass
