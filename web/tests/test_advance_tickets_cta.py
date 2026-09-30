"""The home-page advance-ticket CTA.

Guards the two ways it can go wrong: a Buy Now band still up after the
film has opened, and a pasted link that is not our own Square checkout.
"""

import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from web.constants import ADVANCE_TICKETS


@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_now_showing", return_value=[])
class AdvanceTicketsVisibilityTests(TestCase):
    def _home(self, today):
        with mock.patch("web.views.timezone.localdate", return_value=today):
            return self.client.get(reverse("home")).content.decode()

    def test_renders_before_opening(self, _ns, _cs):
        html = self._home(ADVANCE_TICKETS["until"] - datetime.timedelta(days=30))
        self.assertIn('class="advance-cta"', html)
        self.assertIn(ADVANCE_TICKETS["url"], html)
        self.assertIn(ADVANCE_TICKETS["button"], html)
        self.assertIn(ADVANCE_TICKETS["film"], html)

    def test_still_up_on_opening_day(self, _ns, _cs):
        html = self._home(ADVANCE_TICKETS["until"])
        self.assertIn('class="advance-cta"', html)

    def test_gone_the_day_after_opening(self, _ns, _cs):
        html = self._home(ADVANCE_TICKETS["until"] + datetime.timedelta(days=1))
        self.assertNotIn("advance-cta", html)

    def test_none_is_the_off_switch(self, _ns, _cs):
        with mock.patch("web.views.ADVANCE_TICKETS", None):
            html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("advance-cta", html)

    def test_sits_above_now_showing(self, _ns, _cs):
        html = self._home(ADVANCE_TICKETS["until"] - datetime.timedelta(days=30))
        self.assertLess(html.index('class="advance-cta"'), html.index('id="now-showing"'))

    def test_opens_safely_in_a_new_window(self, _ns, _cs):
        html = self._home(ADVANCE_TICKETS["until"] - datetime.timedelta(days=30))
        self.assertIn('rel="noopener noreferrer"', html)


class AdvanceTicketsLinkTests(TestCase):
    def test_it_is_a_square_link(self):
        self.assertTrue(
            ADVANCE_TICKETS["url"].startswith("https://square.link/u/"),
            ADVANCE_TICKETS["url"],
        )
