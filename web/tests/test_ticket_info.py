"""The "how much, and where do I pay" line under the showtimes.

The audit found the site never said what a ticket costs: TICKET_PRICES fed
the phone line and nothing else, and a movie page's only buying guidance was
one muted sentence. The line reads the same constants the phone line does,
so a reprice moves both.
"""

import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG, TICKET_PRICES

from .test_home_sections import hero_film


def ticket_info(html):
    match = re.search(r'<p class="ticket-info">.*?</p>', html, re.S)
    return match.group(0) if match else None


class TicketInfoContentTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films")
    def test_home_hero_carries_the_prices(self, ns, _cs):
        ns.return_value = [hero_film()]
        line = ticket_info(self.client.get(reverse("home")).content.decode())
        self.assertIsNotNone(line, "no ticket line on the home page")
        p = TICKET_PRICES
        for price in (p["adult"], p["senior"], p["child"], p["matinee"], p["member"]):
            self.assertIn(f"${price}", line)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films")
    def test_says_where_to_pay_and_how_to_call(self, ns, _cs):
        ns.return_value = [hero_film()]
        line = ticket_info(self.client.get(reverse("home")).content.decode())
        self.assertIn("box office", line)
        self.assertIn('href="tel:+12072315287"', line)
        self.assertIn(SITE_CONFIG["cinema"]["phone"], line)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films")
    def test_points_to_online_tickets_and_the_box_office(self, ns, _cs):
        ns.return_value = [hero_film()]
        line = ticket_info(self.client.get(reverse("home")).content.decode())
        self.assertIn(
            "Buy online from the showtimes above, or pay at the box office.", line
        )
        self.assertIn(SITE_CONFIG["cinema"]["address"]["street"], line)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films")
    def test_member_price_links_to_membership(self, ns, _cs):
        ns.return_value = [hero_film()]
        line = ticket_info(self.client.get(reverse("home")).content.decode())
        self.assertIn(f'href="{reverse("membership")}"', line)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_no_prices_when_nothing_is_showing(self, _ns, _cs):
        """Prices with no showtimes to attach them to is a non sequitur."""
        html = self.client.get(reverse("home")).content.decode()
        self.assertIsNone(ticket_info(html))

    @mock.patch.dict(TICKET_PRICES, {"adult": 11})
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films")
    def test_reads_the_live_constants(self, ns, _cs):
        ns.return_value = [hero_film()]
        line = ticket_info(self.client.get(reverse("home")).content.decode())
        self.assertIn("$11", line)
