from django.test import TestCase
from django.urls import reverse


class ChromeTests(TestCase):
    def test_nav_renders_the_logo(self):
        html = self.client.get(reverse("home")).content.decode()
        # The logo is the brand wordmark SVG; its accessible name is the alt.
        self.assertIn("fkc-wordmark-dark.svg", html)
        self.assertIn('alt="Fort Kent Cinema"', html)

    def test_footer_renders_address_and_social(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("13 Hall Street", html)             # address from site_config
        self.assertIn("facebook.com/fortkentcinema", html)  # social link
