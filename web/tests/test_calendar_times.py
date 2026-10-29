"""The Coming Soon calendar: a poster on today or a later day is a button
that opens that day's times for the film, as the same ticket dialog the
Coming Soon card uses. Past days and hidden runs keep plain posters.
"""

import datetime

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from tickets.tests.factories import make_live_item, make_order, make_showtime

from web.tests.test_home_tickets import (
    SQUARE_ON,
    coming_soon_showtime,
    in_days,
    make_showtime_for,
)


def month_url(day):
    return reverse("calendar_month", args=[day.year, day.month - 1])


@override_settings(**SQUARE_ON)
class CalendarTimesTests(TestCase):
    def setUp(self):
        self.st = coming_soon_showtime(days=21)
        make_live_item(self.st.engagement)
        self.day = timezone.localdate() + datetime.timedelta(days=21)
        self.buy_url = reverse("tickets:buy", args=[self.st.pk])
        self.dialog_id = f"calendar-times-{self.day.day}-0"

    def fragment(self, day=None):
        return self.client.get(month_url(day or self.day)).content.decode()

    def dialog(self, html):
        start = html.index(f'id="{self.dialog_id}"')
        end = html.index("</div>\n", html.index("ticket-info", start))
        return html[start:end]

    def test_the_poster_is_a_button_that_opens_the_dialog(self):
        html = self.fragment()
        self.assertIn(
            '<button class="coming-calendar-cell__poster '
            'coming-calendar-cell__poster--times"',
            html,
        )
        self.assertIn(
            f'aria-label="Times for Dune on {self.day.strftime("%a, %b %-d")}"', html
        )
        self.assertIn(f'aria-controls="{self.dialog_id}"', html)

    def test_the_dialog_lists_the_day_with_a_buy_link(self):
        dialog = self.dialog(self.fragment())
        # The day is the eyebrow, in full; the one row carries no label.
        self.assertIn(self.day.strftime("%A, %B %-d"), dialog)
        self.assertNotIn('class="coming-tickets__date"', dialog)
        self.assertIn(
            f'<a class="showtime showtime--buy" href="{self.buy_url}"', dialog
        )
        self.assertIn('role="dialog"', dialog)
        self.assertIn('aria-modal="true"', dialog)
        self.assertIn(f'aria-labelledby="{self.dialog_id}-title"', dialog)
        self.assertIn('aria-label="Close"', dialog)
        self.assertIn("ticket-info", dialog)

    def test_only_that_days_times_are_in_the_dialog(self):
        other = make_showtime_for(self.st, 22, hour=13)
        dialog = self.dialog(self.fragment())
        self.assertIn(self.buy_url, dialog)
        self.assertNotIn(reverse("tickets:buy", args=[other.pk]), dialog)

    def test_sold_out_chip_is_plain_with_note(self):
        self.st.online_allowance = 1
        self.st.save()
        make_order(self.st, status="PAID")
        dialog = self.dialog(self.fragment())
        self.assertNotIn(self.buy_url, dialog)
        self.assertIn("Sold out online", dialog)

    def test_a_past_days_poster_is_a_plain_image(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        past = make_showtime(starts_at=in_days(-1))
        html = self.fragment(yesterday)
        self.assertIn("coming-calendar-cell--past", html)
        self.assertNotIn(f'id="calendar-times-{yesterday.day}-0"', html)
        self.assertNotIn(reverse("tickets:buy", args=[past.pk]), html)

    def test_a_hidden_runs_poster_is_a_plain_image(self):
        self.st.engagement.show_in_main_listings = False
        self.st.engagement.save()
        html = self.fragment()
        self.assertIn("coming-calendar-cell--has-movie", html)
        self.assertNotIn("coming-calendar-cell__poster--times", html)
        self.assertNotIn(f'id="{self.dialog_id}"', html)

    def test_more_showtimes_do_not_add_queries(self):
        with CaptureQueriesContext(connection) as one:
            self.fragment()
        for days in (22, 23):
            make_showtime_for(self.st, days)
        with CaptureQueriesContext(connection) as three:
            html = self.fragment()
        self.assertEqual(html.count('class="showtime__buy"'), 3)
        self.assertEqual(len(three), len(one))
