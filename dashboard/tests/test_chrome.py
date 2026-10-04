import re

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

    def test_nav_order_home_first_then_alphabetical(self) -> None:
        # Home stays on top; everything under it is alphabetical by the label
        # staff see, the order the owner set on 2026-10-03. The mobile menu
        # is this same sidebar slid in, so this pins both.
        html = self.client.get(reverse("dashboard:home")).content.decode()
        nav = html.split('data-cy="sidebar-nav"', 1)[1].split("</nav>", 1)[0]
        labels = re.findall(r"</svg>([^<]+)</a>", nav)
        self.assertEqual(
            labels,
            [
                "Home",
                "Blog",
                "Engagements",
                "Inquiries",
                "Members",
                "Memberships",
                "Polls",
                "Screens",
                "Subscribers",
            ],
        )

    def test_logout_link_present(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("<form", html)
        self.assertIn(f'action="{reverse("logout")}"', html)
        self.assertIn('method="post"', html)
        self.assertIn('data-cy="logout-button"', html)

    def test_logout_get_not_allowed(self) -> None:
        resp = self.client.get("/logout/")
        self.assertEqual(resp.status_code, 405)

    def test_username_rendered(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("staffer", html)

    def test_active_nav_marked(self) -> None:
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        # the Screens link carries the active class on its own page
        self.assertRegex(html, r'href="/dashboard/screens"[^>]*class="[^"]*\bactive\b')
