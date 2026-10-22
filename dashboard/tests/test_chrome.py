import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from dashboard.tests.helpers import make_staff


class ChromeTests(TestCase):
    def setUp(self) -> None:
        self.staff = make_staff(
            username="staffer", password="pw12345"
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
        # A link may end in a count badge (Voicemails); the label precedes it.
        labels = re.findall(r"</svg>([^<]+)(?:<span[^>]*>[^<]*</span>)?</a>", nav)
        self.assertEqual(
            labels,
            [
                "Home",
                "Ad Inquiries",
                "Blog",
                "Engagements",
                "Members",
                "Memberships",
                "Online tickets",
                "Polls",
                "Rental Inquiries",
                "Screens",
                "Subscribers",
                "Voicemails",
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

    def test_sidebar_shows_only_viewable_sections(self) -> None:
        make_staff(username="box", perms=("tickets.view_ticketorder",))
        self.client.login(username="box", password="pw12345")
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(reverse("dashboard:tickets"), html)
        for name in (
            "ad_inquiries",
            "blog",
            "engagements",
            "members",
            "tiers",
            "polls",
            "rental_inquiries",
            "screens",
            "subscribers",
            "voicemails",
        ):
            self.assertNotIn(f'href="{reverse(f"dashboard:{name}")}"', html)
        self.assertNotIn("sidebarBadge", html)
        self.assertNotIn("keyboardHint", html)

    def test_superuser_sees_every_link(self) -> None:
        get_user_model().objects.create_superuser(
            username="root", email="r@example.com", password="pw12345"
        )
        self.client.login(username="root", password="pw12345")
        html = self.client.get(reverse("dashboard:home")).content.decode()
        for name in (
            "ad_inquiries",
            "blog",
            "engagements",
            "members",
            "tiers",
            "tickets",
            "polls",
            "rental_inquiries",
            "screens",
            "subscribers",
            "voicemails",
        ):
            self.assertIn(f'href="{reverse(f"dashboard:{name}")}"', html)
        self.assertIn("keyboardHint", html)

    def test_keyboard_hint_needs_add_engagement(self) -> None:
        make_staff(username="adder", perms=("cinema.add_engagement",))
        self.client.login(username="adder", password="pw12345")
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("keyboardHint", html)
