from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_home_returns_200(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_home_uses_base_and_home_templates(self):
        response = self.client.get(reverse("home"))
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/home.html")


class SiteConfigContextTests(TestCase):
    def test_site_config_available_in_templates(self):
        response = self.client.get(reverse("home"))
        self.assertIn("site_config", response.context)
        self.assertEqual(
            response.context["site_config"]["cinema"]["name"], "Fort Kent Cinema"
        )

    def test_navigation_present(self):
        from web.constants import SITE_CONFIG

        labels = [item["label"] for item in SITE_CONFIG["navigation"]]
        self.assertIn("Now Showing", labels)
        self.assertIn("Blog", labels)
