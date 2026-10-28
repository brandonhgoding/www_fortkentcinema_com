"""Home page showtime chips and ScreeningEvent offers for online tickets.

A purchasable showing's chip links to its ticket page with a "Buy" cue; a
showing sold out online keeps a plain chip with a note; anything else (Square
off, run not pushed, past the cutoff) stays the plain chip it always was.
"""

import datetime
import json
import re
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from tickets.tests.factories import make_live_item, make_order, make_showtime

SQUARE_ON = {
    "SQUARE_ACCESS_TOKEN": "t",
    "SQUARE_LOCATION_ID": "L",
    "SQUARE_TICKET_CATEGORY_ID": "C",
}


def screening_events(html):
    """The @graph of ScreeningEvents: its block has no @type of its own."""
    for raw in re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
    ):
        block = json.loads(raw)
        if "@graph" in block:
            return block["@graph"]
    return None


def in_two_days(hour=19):
    day = timezone.localdate() + datetime.timedelta(days=2)
    return datetime.datetime.combine(
        day, datetime.time(hour, 0), tzinfo=ZoneInfo("America/New_York")
    )


@override_settings(**SQUARE_ON)
class HomeTicketChipTests(TestCase):
    def setUp(self):
        self.st = make_showtime(starts_at=in_two_days())
        make_live_item(self.st.engagement)
        self.buy_url = reverse("tickets:buy", args=[self.st.pk])

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def test_purchasable_chip_is_a_link(self):
        html = self.home()
        self.assertIn(f'<a class="showtime showtime--buy" href="{self.buy_url}"', html)
        self.assertIn('<span class="showtime__buy">Buy</span>', html)
        self.assertNotIn("Sold out online", html)

    def test_sold_out_chip_is_plain_with_note(self):
        self.st.online_allowance = 1
        self.st.save()
        make_order(self.st, status="PAID")
        html = self.home()
        # The JSON-LD offer still names the ticket page; the chip must not.
        self.assertNotIn(f'href="{self.buy_url}"', html)
        self.assertIn('<span class="showtime__note">Sold out online</span>', html)
        self.assertNotIn('class="showtime__buy"', html)

    def test_in_person_only_chip_is_plain_with_note(self):
        self.st.online_allowance = 0
        self.st.save()
        html = self.home()
        self.assertNotIn(self.buy_url, html)
        self.assertIn(
            '<span class="showtime__note">In-person purchase only</span>', html
        )
        self.assertNotIn("Sold out online", html)
        self.assertNotIn('class="showtime__buy"', html)

    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_disabled_square_leaves_plain_chips(self):
        html = self.home()
        self.assertNotIn(self.buy_url, html)
        self.assertNotIn("showtime--buy", html)
        self.assertNotIn("Sold out online", html)
        self.assertIn('<span class="showtime">7:00 PM</span>', html)

    def test_open_captions_note_survives_on_a_buy_link(self):
        self.st.captions = "OC"
        self.st.save()
        html = self.home()
        link = re.search(
            r'<a class="showtime[^"]*" href="%s">.*?</a>' % self.buy_url, html, re.S
        )
        self.assertIsNotNone(link)
        self.assertIn("showtime--noted", link.group(0))
        self.assertIn('class="showtime__note"', link.group(0))

    def test_chip_count_does_not_add_queries(self):
        with CaptureQueriesContext(connection) as one:
            self.home()
        for hour in (13, 16):
            self.st.engagement.showtimes.create(
                screen=self.st.screen, starts_at=in_two_days(hour)
            )
        with CaptureQueriesContext(connection) as three:
            html = self.home()
        # Three times, each on the desktop card, the phone card and the hero.
        self.assertEqual(html.count('class="showtime__buy"'), 3 * 3)
        self.assertEqual(len(three), len(one))


@override_settings(**SQUARE_ON)
class HomeScreeningOfferTests(TestCase):
    def setUp(self):
        self.st = make_showtime(starts_at=in_two_days())
        self.buy_url = "http://testserver" + reverse("tickets:buy", args=[self.st.pk])

    def offers(self):
        (event,) = screening_events(self.client.get(reverse("home")).content.decode())
        return event["offers"]

    def test_purchasable_offer_points_at_the_ticket_page(self):
        make_live_item(self.st.engagement)
        offers = self.offers()
        self.assertEqual(offers["url"], self.buy_url)
        self.assertEqual(offers["availability"], "https://schema.org/InStock")

    def test_sold_out_offer_is_sold_out_and_keeps_the_url(self):
        make_live_item(self.st.engagement)
        self.st.online_allowance = 1
        self.st.save()
        make_order(self.st, status="PAID")
        offers = self.offers()
        self.assertEqual(offers["url"], self.buy_url)
        self.assertEqual(offers["availability"], "https://schema.org/SoldOut")

    def test_in_person_only_offer_is_in_store_only(self):
        make_live_item(self.st.engagement)
        self.st.online_allowance = 0
        self.st.save()
        offers = self.offers()
        self.assertEqual(offers["url"], "http://testserver/#now-showing")
        self.assertEqual(offers["availability"], "https://schema.org/InStoreOnly")

    def test_closed_offer_keeps_the_now_showing_url(self):
        # No live Square item for the run: sales are closed, not sold out.
        offers = self.offers()
        self.assertEqual(offers["url"], "http://testserver/#now-showing")
        self.assertEqual(offers["availability"], "https://schema.org/InStock")
