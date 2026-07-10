from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class DashboardAuthTests(TestCase):
    def setUp(self) -> None:
        self.staff = User.objects.create_user(
            username="staffer", password="pw12345", is_staff=True
        )
        self.plain = User.objects.create_user(
            username="plain", password="pw12345", is_staff=False
        )

    def test_anonymous_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])
        self.assertIn("next=", resp["Location"])

    def test_non_staff_forbidden(self) -> None:
        self.client.login(username="plain", password="pw12345")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 403)

    def test_staff_ok(self) -> None:
        self.client.login(username="staffer", password="pw12345")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 200)

    def test_named_routes_resolve(self) -> None:
        self.assertEqual(reverse("dashboard:home"), "/dashboard/")
        self.assertEqual(reverse("dashboard:screens"), "/dashboard/screens")
        self.assertEqual(reverse("dashboard:engagements"), "/dashboard/engagements")
