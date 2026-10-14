"""Where the mailing-list signup stands on the pages."""

import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from .test_home_sections import movie


def signup_locations(html):
    return re.findall(r'name="location" value="([^"]+)"', html)


@mock.patch("web.views.get_coming_soon", return_value=[])
class HomePlacementTests(TestCase):
    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def test_under_the_showtimes(self, _cs):
        with mock.patch("web.views.get_now_showing", return_value=[movie()]):
            html = self.home()
        self.assertEqual(signup_locations(html), ["home_showtimes"])
        self.assertLess(
            html.index('class="schedule-list"'), html.index('class="list-signup"')
        )
        self.assertIn("every Thursday", html)

    def test_in_the_empty_state_before_the_links(self, _cs):
        with mock.patch("web.views.get_now_showing", return_value=[]):
            html = self.home()
        self.assertEqual(signup_locations(html), ["home_empty"])
        self.assertIn("Get an email the moment new runs are booked.", html)
        self.assertLess(
            html.index('class="list-signup"'), html.index('class="no-showtimes__links"')
        )
