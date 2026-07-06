from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ChromeTests(TestCase):
    def setUp(self) -> None:
        self.staff = User.objects.create_user(
            username="staffer", password="pw12345", is_staff=True
        )
        self.client.login(username="staffer", password="pw12345")

    def test_brand_and_nav_items(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("LeprinceOS", html)
        self.assertIn(">Home<", html)
        self.assertIn(">Engagements<", html)
        self.assertIn(">Screens<", html)
        self.assertNotIn("API Docs", html)

    def test_logout_link_present(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn('href="/logout/"', html)

    def test_username_rendered(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("staffer", html)

    def test_active_nav_marked(self) -> None:
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        # the Screens link carries the active class on its own page
        self.assertRegex(html, r'href="/dashboard/screens"[^>]*class="[^"]*\bactive\b')
