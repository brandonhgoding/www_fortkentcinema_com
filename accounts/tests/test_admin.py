from django.test import TestCase

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
