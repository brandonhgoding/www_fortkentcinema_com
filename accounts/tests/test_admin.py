from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from accounts.tests.factories import make_user


class UserAdminTests(TestCase):
    def setUp(self):
        self.client.force_login(
            User.objects.create_superuser(email="root@example.com", password="pw")
        )

    def add(self, email):
        return self.client.post(
            "/admin/accounts/user/add/",
            {
                "email": email,
                "usable_password": "true",
                "password1": "a-Long-pass-phrase-9",
                "password2": "a-Long-pass-phrase-9",
            },
        )

    def test_add_creates_user_by_normalised_email(self):
        self.assertEqual(self.add(" New@Example.com ").status_code, 302)
        self.assertTrue(User.objects.filter(email="new@example.com").exists())

    def test_add_refuses_email_differing_only_in_case(self):
        make_user(email="staff@example.com")
        resp = self.add("STAFF@example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "A user with that email already exists.")
        self.assertEqual(
            User.objects.filter(email__iexact="staff@example.com").count(), 1
        )

    def test_change_page_shows_email_not_username(self):
        user = make_user(email="staff@example.com")
        html = self.client.get(
            f"/admin/accounts/user/{user.pk}/change/"
        ).content.decode()
        self.assertIn('name="email"', html)
        self.assertNotIn('name="username"', html)


class UserAdminVerifiedTests(TestCase):
    def setUp(self):
        self.client.force_login(
            User.objects.create_superuser(email="root@example.com", password="pw")
        )

    def test_user_added_in_admin_is_stamped_verified(self):
        self.client.post(
            "/admin/accounts/user/add/",
            {
                "email": "made@example.com",
                "usable_password": "true",
                "password1": "a-Long-pass-phrase-9",
                "password2": "a-Long-pass-phrase-9",
            },
        )
        self.assertIsNotNone(
            User.objects.get(email="made@example.com").email_verified_at
        )

    def test_promoting_to_staff_stamps_verified(self):
        user = make_user("m@example.com", is_staff=False)
        self.assertIsNone(user.email_verified_at)
        self.client.post(
            f"/admin/accounts/user/{user.pk}/change/",
            {
                "email": "m@example.com",
                "is_active": "on",
                "is_staff": "on",
                "date_joined_0": "2026-10-01",
                "date_joined_1": "12:00:00",
            },
        )
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertIsNotNone(user.email_verified_at)

    def test_editing_a_member_leaves_them_unverified(self):
        user = make_user("m@example.com", is_staff=False)
        self.client.post(
            f"/admin/accounts/user/{user.pk}/change/",
            {
                "email": "m@example.com",
                "is_active": "on",
                "date_joined_0": "2026-10-01",
                "date_joined_1": "12:00:00",
            },
        )
        user.refresh_from_db()
        self.assertIsNone(user.email_verified_at)

    def test_mark_email_verified_action(self):
        a = make_user("a@example.com", is_staff=False)
        b = make_user("b@example.com", is_staff=False)
        earlier = timezone.now() - timedelta(days=3)
        User.objects.filter(pk=b.pk).update(email_verified_at=earlier)
        self.client.post(
            "/admin/accounts/user/",
            {
                "action": "mark_email_verified",
                "_selected_action": [a.pk, b.pk],
            },
        )
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertIsNotNone(a.email_verified_at)
        self.assertEqual(b.email_verified_at, earlier)
