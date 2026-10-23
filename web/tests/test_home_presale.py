"""The Graduate pre-sale banner is gone (2026-10-23).

The banner ran on the home page from 2026-10-17 and was to hide itself the
day after its October 24 deadline. The owner asked for it to be removed a
day early, outright: no section, no hero caption, no Square link, and no
poster assets left behind for the next page to pick up.
"""

from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

SQUARE = "https://square.link/u/EYztfLV6"


@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_now_showing", return_value=[])
class HomePresaleGoneTests(TestCase):
    def test_home_has_no_presale_before_the_old_deadline(self, *_):
        with mock.patch("web.views.today_eastern", return_value="2026-10-23"):
            html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn('id="presale"', html)
        self.assertNotIn('href="#presale"', html)
        self.assertNotIn("The Graduate", html)
        self.assertNotIn(SQUARE, html)
        self.assertNotIn("graduate-presale", html)


class PresaleAssetsGoneTests(TestCase):
    def test_banner_images_are_removed(self):
        img = Path(settings.BASE_DIR) / "static" / "img"
        self.assertEqual(sorted(img.glob("graduate-presale-*")), [])
