"""The public /sponsor/ page is gone: no routes, no links, no mentions."""

from unittest import mock

from django.test import TestCase
from django.urls import NoReverseMatch, reverse


class SponsorPageRemovedTests(TestCase):
    def test_pages_are_404(self):
        for path in (
            "/sponsor/",
            "/sponsor/inquire",
            "/sponsor/catalog",
            "/sponsor/films",
            "/sponsor/?sort=title",
            "/sponsor/catalog?q=x",
        ):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_route_names_gone(self):
        for name in ("sponsor", "sponsor_inquire", "sponsor_catalog", "sponsor_films"):
            with self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_not_in_sitemap(self):
        self.assertNotContains(self.client.get("/sitemap.xml"), "/sponsor")

    def test_not_in_llms_txt(self):
        body = self.client.get("/llms.txt").content.decode().lower()
        self.assertNotIn("sponsor", body)

    @mock.patch("web.views.get_now_showing", return_value=[])
    @mock.patch("web.views.get_coming_soon", return_value=[])
    def test_coming_soon_empty_state_has_no_sponsor_link(self, *_):
        html = self.client.get(reverse("home")).content.decode().lower()
        self.assertNotIn("sponsor it", html)
        self.assertNotIn("/sponsor/", html)


class HomeSponsorshipRemovedTests(TestCase):
    def test_home_has_no_banner_or_support_strip(self):
        html = self.client.get(reverse("home")).content.decode()
        for needle in (
            "sponsored-cta",
            'id="support"',
            "sponsor_click",
            "donate_click",
            "sponsored_cta_click",
        ):
            self.assertNotIn(needle, html, needle)

    def test_constants_gone(self):
        from web import constants

        for name in (
            "SPONSORED_SCREENING",
            "SHOW_SUPPORT_STRIP",
            "DONATION",
            "SPONSORSHIP_TIERS",
        ):
            self.assertFalse(hasattr(constants, name), name)
