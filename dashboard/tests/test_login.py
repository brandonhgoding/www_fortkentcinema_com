from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class LoginTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="staffer", password="pw12345", is_staff=True)

    def test_login_page_themed(self) -> None:
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("LeprinceOS", html)
        self.assertIn("login.css", html)

    def test_login_redirects_to_dashboard(self) -> None:
        resp = self.client.post(
            "/login", {"username": "staffer", "password": "pw12345"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/dashboard/")

    def test_logout_works(self) -> None:
        self.client.login(username="staffer", password="pw12345")
        resp = self.client.post("/logout/")
        self.assertEqual(resp.status_code, 302)
