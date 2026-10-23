"""The public /sponsor/ page is gone: no routes, no links, no mentions."""

from unittest import mock

from django.apps import apps
from django.contrib import admin
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from dashboard.tests.helpers import make_staff


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


class DashboardSponsorshipRemovedTests(TestCase):
    def test_dashboard_inquiries_gone(self):
        with self.assertRaises(NoReverseMatch):
            reverse("dashboard:inquiries")
        with self.assertRaises(NoReverseMatch):
            reverse("dashboard:inquiry_status", args=[1])
        staff = make_staff(
            email="staff@example.com", password="pw"
        )
        self.client.force_login(staff)
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertNotIn("/dashboard/inquiries", html)
        self.assertIn("Rental Inquiries", html)


class AdminCommandsRemovedTests(TestCase):
    def test_commands_gone(self):
        for name in ("import_studio_catalog", "render_promo_cards"):
            with self.assertRaises(CommandError, msg=name):
                call_command(name)

    def test_admin_unregistered(self):
        gone = {"studio", "studiotitle", "sponsorshipinquiry"}
        registered = {m._meta.model_name for m in admin.site._registry}
        self.assertFalse(registered & gone)


class ModelsRemovedTests(TestCase):
    def test_models_gone(self):
        from cinema.models import Film

        for name in ("Studio", "StudioTitle", "SponsorshipInquiry"):
            with self.assertRaises(LookupError, msg=name):
                apps.get_model("cinema", name)
        self.assertNotIn("studio_titles", [f.name for f in Film._meta.get_fields()])
