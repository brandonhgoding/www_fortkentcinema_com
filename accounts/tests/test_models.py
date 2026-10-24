from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from accounts.tests.factories import make_user

User = get_user_model()


class UserModelTests(TestCase):
    def test_save_strips_and_lowercases_email(self):
        self.assertEqual(
            make_user(email="  Staff@Example.COM ").email, "staff@example.com"
        )

    def test_email_unique_ignoring_case_at_the_database(self):
        make_user(email="a@example.com")
        with self.assertRaises(IntegrityError):
            # bulk_create skips save(), so only the constraint can refuse it.
            User.objects.bulk_create([User(email="A@example.com")])

    def test_create_user_refuses_blank_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="  ", password="pw")

    def test_create_superuser_sets_flags(self):
        u = User.objects.create_superuser(email="Root@Example.com", password="pw")
        self.assertEqual(
            (u.email, u.is_staff, u.is_superuser),
            ("root@example.com", True, True),
        )

    def test_login_ignores_email_case(self):
        make_user(email="staff@example.com", password="pw12345")
        self.assertTrue(
            self.client.login(username="Staff@Example.com", password="pw12345")
        )

    def test_names_are_the_email(self):
        user = make_user(email="a@example.com")
        self.assertEqual(user.get_short_name(), "a@example.com")
        self.assertEqual(user.get_full_name(), "a@example.com")

    def test_stores_no_personal_names(self):
        fields = [f.name for f in User._meta.get_fields()]
        self.assertNotIn("first_name", fields)
        self.assertNotIn("last_name", fields)

    def test_has_no_username_field(self):
        self.assertNotIn("username", [f.name for f in User._meta.get_fields()])
