# Strawberry Django JWT

[![PyPI - Downloads](https://img.shields.io/pypi/dm/strawberry-django-jwt?style=for-the-badge)](https://pypi.org/project/strawberry-django-jwt/)

[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/KundaPanda/strawberry-django-jwt?style=for-the-badge)](https://github.com/KundaPanda/strawberry-django-jwt/graphs/commit-activity)
![GitHub last commit](https://img.shields.io/github/last-commit/KundaPanda/strawberry-django-jwt?style=for-the-badge)

![Codecov](https://img.shields.io/codecov/c/github/KundaPanda/strawberry-django-jwt?style=for-the-badge)
[![Codacy grade](https://img.shields.io/codacy/grade/aa892e1ed8924429af95d9eeaa495338?style=for-the-badge)](https://www.codacy.com/gh/KundaPanda/strawberry-django-jwt/dashboard?utm_source=github.com&utm_medium=referral&utm_content=KundaPanda/strawberry-django-jwt&utm_campaign=Badge_Grade)

[JSON Web Token](https://jwt.io/>) authentication
for [Strawberry Django GraphQL](https://strawberry.rocks/docs/integrations/django)

---

## Disclaimer

This project is a forked version of [Django GraphQL JWT](https://github.com/flavors/django-graphql-jwt) that
substitutes [Graphene](https://graphene-python.org/) GraphQL backend for [Strawberry](https://strawberry.rocks/)

---

## Installation

1. Install last stable version from Pypi:

   ```shell
   pip install strawberry-django-jwt
   ```

2. Add `AuthenticationMiddleware` middleware to your **MIDDLEWARE** settings:

   ```python
   MIDDLEWARE = [
       ...,
       'django.contrib.auth.middleware.AuthenticationMiddleware',
       ...,
   ]
   ```

3. Add `JSONWebTokenMiddleware` or `AsyncJSONWebTokenMiddleware` middleware to your **STRAWBERRY** schema definition:

   ```python
   from strawberry_django_jwt.middleware import JSONWebTokenMiddleware, AsyncJSONWebTokenMiddleware
   from strawberry import Schema

   schema = Schema(...)
   schema.middleware.extend([
        # !! IMPORTANT !!
        # Pick only one, async middleware is needed when using AsyncGraphQLSchema
        JSONWebTokenMiddleware(),
        AsyncJSONWebTokenMiddleware(),
   ])
   ```

4. Add `JSONWebTokenBackend` backend to your **AUTHENTICATION_BACKENDS**:

   ```python
   AUTHENTICATION_BACKENDS = [
       'strawberry_django_jwt.backends.JSONWebTokenBackend',
       'django.contrib.auth.backends.ModelBackend',
   ]
   ```

5. Add _strawberry-django-jwt_ mutations to the root schema:

   ```python
   import strawberry
   import strawberry_django_jwt.mutations as jwt_mutations

   @strawberry.type
   class Mutation:
       token_auth = jwt_mutations.ObtainJSONWebToken.obtain
       verify_token = jwt_mutations.Verify.verify
       refresh_token = jwt_mutations.Refresh.refresh
       delete_token_cookie = jwt_mutations.DeleteJSONWebTokenCookie.delete_cookie


   schema = strawberry.Schema(mutation=Mutation, query=...)
   ```

6. \[OPTIONAL\] Set up the custom Strawberry views

   These views set the status code of failed authentication attempts to 401 instead of the default 200.

   ```python
   from django.urls import re_path
   from strawberry_django_jwt.decorators import jwt_cookie
   from strawberry_django_jwt.views import StatusHandlingGraphQLView as GQLView
   from ... import schema

   urlpatterns += \
    [
        re_path(r'^graphql/?$', jwt_cookie(GQLView.as_view(schema=schema))),
    ]
   ```

   or, for async views:

   ```python
   from django.urls import re_path
   from strawberry_django_jwt.decorators import jwt_cookie
   from strawberry_django_jwt.views import AsyncStatusHandlingGraphQLView as AGQLView
   from ... import schema

   urlpatterns += \
    [
        re_path(r'^graphql/?$', jwt_cookie(AGQLView.as_view(schema=schema))),
    ]
   ```

---

## Quickstart Documentation

===============_Work in Progress_===============

Relay support has been temporarily removed due to lack of experience with Relay

Most of the features are conceptually the same as those provided
by [Django GraphQL JWT](https://github.com/flavors/django-graphql-jwt)

### Authenticating fields

Fields can be set to auth-only using the `login_required` decorator in combination with `strawberry.field` or
via `login_field`

```python
import strawberry
from strawberry.types import Info
from strawberry_django_jwt.decorators import login_required


def auth_field(fn=None):
    return strawberry.field(login_required(fn))


@strawberry.type
class Query:
    @auth_field
    def hello(self, info: Info) -> str:
        return "World"

    @strawberry.field
    @login_required
    def foo(self, info: Info) -> str:
        return "Bar"
```

Please note the info argument, without which strawberry would not provide the context info required for authentication.

### Mixin info injection

An alternative approach to this problem is following:

```python
import strawberry
from strawberry.types import Info
from strawberry_django_jwt.decorators import login_required, login_field
from strawberry_django_jwt.mixins import RequestInfoMixin


@strawberry.type
class Query(RequestInfoMixin):
    @login_field
    def hello(self) -> str:
        # self == { 'info': ... } in this case
        return "World"

    @strawberry.field
    @login_required
    def foo(self) -> str:
        # self == { 'info': ... } in this case
        return self.get("info").field_name

    @strawberry.field
    @login_required
    def explicit_foo(self, info: Info) -> str:
        # self == { } in this case
        return info.field_name
```

`RequestInfoMixin` automatically injects info arguments to all fields in the class.

All function arguments that are not present in the definition will be added by the `login_required` decorator to
the `self` dictionary as kwargs.

### Model mutations

You can add the login_required decorator to them as well

```python
import strawberry
from strawberry_django_jwt.decorators import login_required
from strawberry_django_jwt.mixins import RequestInfoMixin
from strawberry.django import mutations


@strawberry.type
class Mutation(RequestInfoMixin):
    foo_create: FooType = login_required(mutations.create(FooInput))
    foo_delete: FooType = login_required(mutations.update(FooPartialInput))
    foo_update: FooType = login_required(mutations.delete())
```

### Async views

Should be fully supported :)

```python
import strawberry
from strawberry_django_jwt.decorators import login_field
from strawberry_django_jwt.mixins import RequestInfoMixin


@strawberry.type
class Query(RequestInfoMixin):
    @login_field
    async def foo(self) -> str:
        return "bar"
```
