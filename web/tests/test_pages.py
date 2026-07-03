from django.test import TestCase
from django.urls import reverse
from django.contrib.staticfiles.finders import find


class HomePageTests(TestCase):
    def test_home_returns_200(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_home_uses_base_and_home_templates(self):
        response = self.client.get(reverse("home"))
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/home.html")

    def test_no_template_comment_leaks_into_page(self):
        # Django's {# #} comment is single-line only; a multi-line {# #} leaks
        # as literal page text. Guard against that regression.
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("Twitter/X falls back", html)
        self.assertNotIn("{#", html)
        self.assertNotIn("{% comment %}", html)


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


class BaseChromeTests(TestCase):
    def test_default_meta_and_og(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode()
        self.assertIn('property="og:title"', html)
        self.assertIn('property="og:type"', html)
        self.assertIn('name="twitter:card"', html)

    def test_structured_data_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('"@type": "MovieTheater"', html)
        self.assertIn("13 Hall Street", html)

    def test_google_analytics_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("G-S2PR27SWGD", html)

    def test_chrome_elements_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="skip-link"', html)
        self.assertIn("fx-dust", html)
        self.assertIn("data-ambient-dust", html)

    def test_canonical_uses_request_url(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('rel="canonical"', html)


class StaticAssetsTests(TestCase):
    def test_core_css_present(self):
        for name in ("css/variables.css", "css/global.css", "css/effects.css"):
            self.assertIsNotNone(find(name), f"missing static asset: {name}")

    def test_component_css_present(self):
        # Representative sample of the ported component/page sheets.
        for name in ("css/Hero.css", "css/Nav.css", "css/Footer.css", "css/NowShowing.css"):
            self.assertIsNotNone(find(name), f"missing static asset: {name}")
