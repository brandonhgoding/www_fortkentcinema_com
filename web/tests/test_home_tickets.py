"""Home page showtime chips and the ScreeningEvent markup, plus helpers the
other home-page tests share.

Every chip is information only (tickets are bought at the box office), and
only the Now Showing hero lists them. Each showing there is one
ScreeningEvent whose offer names the hero.
"""

import datetime
import json
import re
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cinema.tests.factories import make_showtime

CHIP = '<span class="showtime">'


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


class HomeChipTests(TestCase):
    def setUp(self):
        self.st = make_showtime(starts_at=in_two_days())

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def test_chip_is_the_plain_time(self):
        self.assertIn(f"{CHIP}7:00 PM</span>", self.home())

    def test_open_captions_chip_carries_the_badge(self):
        self.st.captions = "OC"
        self.st.save()
        chip = re.search(r'<span class="showtime">7:00 PM.*?</span></span>',
                         self.home(), re.S)
        self.assertIsNotNone(chip)
        self.assertIn(">OC</abbr>", chip.group(0))
        self.assertIn('<span class="sr-only">Open Captions</span>', chip.group(0))

    def test_chip_count_does_not_add_queries(self):
        with CaptureQueriesContext(connection) as one:
            self.home()
        for hour in (13, 16):
            self.st.engagement.showtimes.create(
                screen=self.st.screen, starts_at=in_two_days(hour)
            )
        with CaptureQueriesContext(connection) as three:
            html = self.home()
        # Three times, each once: the hero is the listing.
        self.assertEqual(html.count(CHIP), 3)
        self.assertEqual(len(three), len(one))


class HomeScreeningOfferTests(TestCase):
    def test_offer_is_in_stock_and_points_at_now_showing(self):
        make_showtime(starts_at=in_two_days())
        (event,) = screening_events(self.client.get(reverse("home")).content.decode())
        self.assertEqual(event["offers"]["url"], "http://testserver/#now-showing")
        self.assertEqual(event["offers"]["availability"], "https://schema.org/InStock")


def in_days(days, hour=19):
    day = timezone.localdate() + datetime.timedelta(days=days)
    return datetime.datetime.combine(
        day, datetime.time(hour, 0), tzinfo=ZoneInfo("America/New_York")
    )


def coming_soon_showtime(days=21, hour=19, **over):
    """A showing of a run that starts `days` out: past the hero's week, so
    its only listing is the Coming Soon card."""
    st = make_showtime(starts_at=in_days(days, hour), **over)
    day = timezone.localdate() + datetime.timedelta(days=days)
    st.engagement.start_date = day
    st.engagement.end_date = day + datetime.timedelta(days=6)
    st.engagement.save()
    return st


def coming_soon_section(html):
    return html[html.index('id="coming-soon"'):]
