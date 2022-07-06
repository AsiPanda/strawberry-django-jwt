import django
from django.contrib.auth.models import AnonymousUser, Permission

from strawberry_django_jwt import decorators, exceptions

from .decorators import OverrideJwtSettings
from .testcases import TestCase


class UserPassesTests(TestCase):
    def test_user_passes_test(self):
        result = decorators.user_passes_test(lambda u: u.pk == self.user.pk,)(
            lambda src, info: None
        )(None, info=self.info(self.user))

        self.assertIsNone(result)

    def test_permission_denied(self):
        func = decorators.user_passes_test(
            lambda u: u.pk == self.user.pk + 1,
        )(lambda src, info: None)

        with self.assertRaises(exceptions.PermissionDenied):
            func(None, info=self.info(self.user))


class LoginRequiredTests(TestCase):
    def test_login_required(self):
        result = decorators.login_required(
            lambda src, info: None,
        )(None, info=self.info(self.user))

        self.assertIsNone(result)

    def test_login_required_no_info(self):
        result = decorators.login_required(
            lambda src, info: None,
        )(None, info=self.info(self.user))

        self.assertIsNone(result)

    def test_permission_denied(self):
        func = decorators.login_required(lambda src, info: None)

        with self.assertRaises(exceptions.PermissionDenied):
            func(None, info=self.info(AnonymousUser()))


class StaffMemberRequiredTests(TestCase):
    def test_staff_member_required(self):
        self.user.is_staff = True

        result = decorators.staff_member_required(
            lambda src, info: None,
        )(None, info=self.info(self.user))

        self.assertIsNone(result)

    def test_permission_denied(self):
        func = decorators.staff_member_required(lambda src, info: None)

        with self.assertRaises(exceptions.PermissionDenied):
            func(None, info=self.info(self.user))


class SuperuserRequiredTests(TestCase):
    def test_superuser_required(self):
        self.user.is_superuser = True

        result = decorators.superuser_required(
            lambda src, info: None,
        )(None, info=self.info(self.user))

        self.assertIsNone(result)

    def test_permission_denied(self):
        func = decorators.superuser_required(lambda src, info: None)

        with self.assertRaises(exceptions.PermissionDenied):
            func(None, info=self.info(self.user))


class PermissionRequiredTests(TestCase):
    def test_permission_required(self):
        perm = Permission.objects.get(codename="add_user")
        self.user.user_permissions.add(perm)

        result = decorators.permission_required("auth.add_user")(
            lambda src, info: None,
        )(None, info=self.info(self.user))

        self.assertIsNone(result)

    def test_permission_denied(self):
        func = decorators.permission_required(
            ["auth.add_user", "auth.change_user"],
        )(lambda src, info: None)

        with self.assertRaises(exceptions.PermissionDenied):
            func(None, info=self.info(self.user))


class CSRFRotationTests(TestCase):
    @OverrideJwtSettings(JWT_CSRF_ROTATION=True)
    def test_csrf_rotation(self):
        info_mock = self.info(AnonymousUser())
        decorators.csrf_rotation(
            lambda cls, info, *args, **kwargs: None,
        )(self, info_mock)
        if django.VERSION >= (4, 0):
            self.assertTrue(info_mock.context.META["CSRF_COOKIE_NEEDS_UPDATE"])
        else:
            self.assertTrue(info_mock.context.csrf_cookie_needs_reset)


class HelperDecoratorTests(TestCase):
    @OverrideJwtSettings(JWT_CSRF_ROTATION=True)
    def test_dispose_extra_kwargs(self):
        def accept_fn(cls, *args, **kwargs):
            return {"self": cls, "args": len(args), "kwargs": len(kwargs)}

        result = decorators.dispose_extra_kwargs(accept_fn)(self, 1, 2, x=5, y=6)

        # self is preserved, 1 is disposed as the "None" root object, args are [2, {**kwargs}]
        self.assertDictEqual(result, {"self": self, "args": 2, "kwargs": 0})
