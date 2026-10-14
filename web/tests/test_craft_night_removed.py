"""Craft Night was deleted on 2026-10-13 (the owner's call). It may come
back; the page, its service and its tests are in git history from before
that date."""

from django.test import TestCase
from django.urls import NoReverseMatch, reverse


class CraftNightRemovedTests(TestCase):
    def test_page_is_gone(self):
        self.assertEqual(self.client.get("/craft-night/").status_code, 404)

    def test_route_is_gone(self):
        with self.assertRaises(NoReverseMatch):
            reverse("craft_night")

    def test_not_in_the_sitemap(self):
        self.assertNotContains(self.client.get("/sitemap.xml"), "craft-night")

    def test_not_in_llms_txt(self):
        self.assertNotContains(self.client.get("/llms.txt"), "Craft Night")
