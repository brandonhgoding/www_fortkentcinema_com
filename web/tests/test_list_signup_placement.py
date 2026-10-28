"""Where the mailing-list signup stands on the pages."""

import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from .test_home_sections import hero_film


def signup_locations(html):
    return re.findall(r'name="location" value="([^"]+)"', html)


@mock.patch("web.views.get_coming_soon", return_value=[])
class HomePlacementTests(TestCase):
    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def test_at_the_foot_of_coming_soon(self, _cs):
        """In a booked week the hero is the listing, and the form closes
        Coming Soon: next runs are what the email is about."""
        with mock.patch("web.views.get_hero_films", return_value=[hero_film()]):
            html = self.home()
        self.assertEqual(signup_locations(html), ["home_showtimes"])
        coming = html[html.index('id="coming-soon"'):]
        coming = coming[: coming.index("</section>")]
        self.assertLess(
            coming.index("coming-calendar-container"),
            coming.index('class="list-signup"'),
        )
        self.assertIn("every Thursday", html)

    def test_in_the_empty_state_before_the_links(self, _cs):
        with mock.patch("web.views.get_hero_films", return_value=[]):
            html = self.home()
        self.assertEqual(signup_locations(html), ["home_empty"])
        self.assertIn("Get an email the moment new runs are booked.", html)
        self.assertLess(
            html.index('class="list-signup"'), html.index('class="no-showtimes__links"')
        )
