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

    def test_open_captions_chip_survives_on_a_buy_link(self):
        self.st.captions = "OC"
        self.st.save()
        html = self.home()
        link = re.search(
            r'<a class="showtime[^"]*" href="%s">.*?</a>' % self.buy_url, html, re.S
        )
        self.assertIsNotNone(link)
        self.assertIn(">OC</abbr>", link.group(0))
        self.assertIn('<span class="sr-only">Open Captions</span>', link.group(0))
        # The chip alone: no sentence, so the pill keeps the row's height.
        self.assertNotIn("showtime--noted", link.group(0))
        self.assertNotIn("showtime__note", link.group(0))

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
        self.assertEqual(html.count('class="showtime__buy"'), 3)
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


@override_settings(**SQUARE_ON)
class ComingSoonTicketChipTests(TestCase):
    """A run beyond the hero's week sells from its Coming Soon card: a
    "Showtimes & tickets" button opens a dialog listing the run's showtimes
    as the same chips the hero uses. The card itself stays as it was."""

    def setUp(self):
        self.st = coming_soon_showtime()
        make_live_item(self.st.engagement)
        self.buy_url = reverse("tickets:buy", args=[self.st.pk])

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def dialog(self, html):
        """The run's ticket dialog, by its anchor id."""
        card = coming_soon_section(html)
        start = card.index('id="coming-tickets-1"')
        return card[start : card.index("</div>\n", card.index("ticket-info", start))]

    def test_the_card_has_a_button_that_is_the_dialog_anchor(self):
        card = coming_soon_section(self.home())
        self.assertIn(
            '<a class="coming-movie-tickets" href="#coming-tickets-1"', card
        )
        self.assertIn("Showtimes &amp; tickets", card)

    def test_the_chips_live_in_the_dialog_not_the_card_body(self):
        html = self.home()
        card = coming_soon_section(html)
        body = card[: card.index('id="coming-tickets-1"')]
        self.assertNotIn(self.buy_url, body)
        dialog = self.dialog(html)
        self.assertIn(
            f'<a class="showtime showtime--buy" href="{self.buy_url}"', dialog
        )
        self.assertIn('<span class="showtime__buy">Buy</span>', dialog)

    def test_the_dialog_names_the_date_of_each_row(self):
        dialog = self.dialog(self.home())
        day = timezone.localdate() + datetime.timedelta(days=21)
        self.assertIn(day.strftime("%a, %b %-d"), dialog)

    def test_the_dialog_is_a_labelled_modal_with_a_close_button(self):
        dialog = self.dialog(self.home())
        self.assertIn('role="dialog"', dialog)
        self.assertIn('aria-modal="true"', dialog)
        self.assertIn('aria-labelledby="coming-tickets-1-title"', dialog)
        self.assertIn('id="coming-tickets-1-title"', dialog)
        self.assertIn('aria-label="Close"', dialog)
        self.assertIn("ticket-info", dialog)

    def test_every_date_is_listed_with_no_fold(self):
        for days in (22, 23, 24):
            make_showtime_for(self.st, days)
        dialog = self.dialog(self.home())
        self.assertEqual(dialog.count('class="showtime__buy"'), 4)
        self.assertNotIn("Show all", dialog)

    def test_sold_out_chip_is_plain_with_note(self):
        self.st.online_allowance = 1
        self.st.save()
        make_order(self.st, status="PAID")
        dialog = self.dialog(self.home())
        self.assertNotIn(self.buy_url, dialog)
        self.assertIn("Sold out online", dialog)

    def test_disabled_square_leaves_plain_chips(self):
        with override_settings(SQUARE_ACCESS_TOKEN=""):
            dialog = self.dialog(self.home())
        self.assertNotIn(self.buy_url, dialog)
        self.assertIn('<span class="showtime">7:00 PM</span>', dialog)

    def test_a_run_with_no_showtimes_has_no_button_and_no_dialog(self):
        self.st.delete()
        card = coming_soon_section(self.home())
        self.assertNotIn("coming-movie-tickets", card)
        self.assertNotIn('id="coming-tickets-1"', card)

    def test_without_javascript_the_dialogs_show_inline(self):
        # The button is an anchor to the dialog's id, and a noscript rule
        # shows the hidden dialogs in place under the grid.
        card = coming_soon_section(self.home())
        self.assertIn("<noscript><style>.coming-tickets-overlay[x-cloak]", card)

    def test_more_chips_do_not_add_queries(self):
        with CaptureQueriesContext(connection) as one:
            self.home()
        for days in (22, 23):
            make_showtime_for(self.st, days)
        with CaptureQueriesContext(connection) as three:
            html = self.home()
        self.assertEqual(coming_soon_section(html).count('class="showtime__buy"'), 3)
        self.assertEqual(len(three), len(one))

    def test_the_offer_points_at_the_ticket_page(self):
        (event,) = screening_events(self.home())
        self.assertEqual(event["offers"]["url"], "http://testserver" + self.buy_url)
        self.assertEqual(event["offers"]["availability"], "https://schema.org/InStock")

    def test_a_run_in_the_hero_and_coming_soon_is_marked_up_once(self):
        # Starts the day after tomorrow: within the hero's week and, starting
        # tomorrow or later, on a Coming Soon card too. One event, not two.
        near = coming_soon_showtime(days=2)
        make_live_item(near.engagement, prefix="near-")
        events = screening_events(self.home())
        urls = sorted(e["offers"]["url"] for e in events)
        self.assertEqual(
            urls,
            sorted(
                "http://testserver" + reverse("tickets:buy", args=[pk])
                for pk in (self.st.pk, near.pk)
            ),
        )


def make_showtime_for(st, days, hour=19):
    """Another showing of `st`'s run, `days` out at `hour`."""
    from cinema.models import Showtime

    return Showtime.objects.create(
        engagement=st.engagement, screen=st.screen, starts_at=in_days(days, hour)
    )


@override_settings(**SQUARE_ON)
class ComingSoonClosedOfferTests(TestCase):
    def test_a_closed_offer_points_at_coming_soon_not_the_hero(self):
        # No live Square item: sales closed, the door still sells it. The run
        # is past the hero's week, so the offer names the card's section.
        coming_soon_showtime()
        (event,) = screening_events(self.client.get(reverse("home")).content.decode())
        self.assertEqual(event["offers"]["url"], "http://testserver/#coming-soon")
        self.assertEqual(event["offers"]["availability"], "https://schema.org/InStock")
