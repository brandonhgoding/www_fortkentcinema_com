from django.test import TestCase
from django.urls import reverse


class ChromeTests(TestCase):
    def test_nav_renders_logo_and_links(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="nav-logo"', html)
        self.assertIn("FORT KENT CINEMA", html)          # logo = cinema name uppercased
        self.assertIn('class="nav-link"', html)
        self.assertIn("/blog", html)                      # a route nav item
        self.assertIn('class="nav-hamburger"', html)      # mobile toggle present

    def test_footer_renders_address_and_social(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="footer"', html)
        self.assertIn("13 Hall Street", html)             # address from site_config
        self.assertIn("facebook.com/fortkentcinema", html)  # social link
        self.assertIn("All rights reserved", html)        # copyright line
