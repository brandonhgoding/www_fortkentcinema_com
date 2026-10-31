"""The Coming Soon calendar: a poster on today or a later day is a button
that opens that day's times for the film, as the same showtimes dialog the
Coming Soon card uses. Past days and hidden runs keep plain posters.
"""

import datetime
import re

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cinema.tests.factories import make_showtime
from web.tests.test_home_tickets import (
    CHIP,
    coming_soon_showtime,
    in_days,
    make_showtime_for,
)


def month_url(day):
    return reverse("calendar_month", args=[day.year, day.month - 1])


def dialog_ids(html):
    return set(re.findall(r'id="(calendar-times-[^"]+)"', html))


class CalendarTimesTests(TestCase):
    def setUp(self):
        self.st = coming_soon_showtime(days=21)
        self.day = timezone.localdate() + datetime.timedelta(days=21)
        self.dialog_id = f"calendar-times-{self.day.isoformat()}-0"

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

    def test_the_dialog_lists_the_day_and_its_time(self):
        dialog = self.dialog(self.fragment())
        # The day is the eyebrow, in full; the one row carries no label.
        self.assertIn(self.day.strftime("%A, %B %-d"), dialog)
        self.assertNotIn('class="coming-tickets__date"', dialog)
        self.assertIn(f"{CHIP}7:00 PM</span>", dialog)
        self.assertIn('role="dialog"', dialog)
        self.assertIn('aria-modal="true"', dialog)
        self.assertIn(f'aria-labelledby="{self.dialog_id}-title"', dialog)
        self.assertIn('aria-label="Close"', dialog)
        self.assertIn("ticket-info", dialog)

    def test_only_that_days_times_are_in_the_dialog(self):
        make_showtime_for(self.st, 22, hour=13)
        dialog = self.dialog(self.fragment())
        self.assertIn(f"{CHIP}7:00 PM</span>", dialog)
        self.assertNotIn("1:00 PM", dialog)
        self.assertEqual(dialog.count(CHIP), 1)

    def test_a_past_days_poster_is_a_plain_image(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        make_showtime(starts_at=in_days(-1))
        html = self.fragment(yesterday)
        self.assertIn("coming-calendar-cell--past", html)
        self.assertNotIn(f'id="calendar-times-{yesterday.isoformat()}-0"', html)

    def test_a_hidden_runs_poster_is_a_plain_image(self):
        self.st.engagement.show_in_main_listings = False
        self.st.engagement.save()
        html = self.fragment()
        self.assertIn("coming-calendar-cell--has-movie", html)
        self.assertNotIn("coming-calendar-cell__poster--times", html)
        self.assertNotIn(f'id="{self.dialog_id}"', html)

    def test_two_months_never_share_a_dialog_id(self):
        # The arrows swap the month fragment with HTMX, which matches new
        # elements to old ones by id to settle their attributes: a dialog
        # whose id repeats in the next month comes back visible with no way
        # to close it. So the id names the date, not just the day of the month.
        today = timezone.localdate()
        first_next = (today.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        first_after = (first_next + datetime.timedelta(days=32)).replace(day=1)
        st = coming_soon_showtime(days=(first_next - today).days)
        make_showtime_for(st, (first_after - today).days)
        next_month = dialog_ids(self.fragment(first_next))
        month_after = dialog_ids(self.fragment(first_after))
        self.assertTrue(next_month and month_after)
        self.assertFalse(next_month & month_after)

    def test_more_showtimes_do_not_add_queries(self):
        with CaptureQueriesContext(connection) as one:
            self.fragment()
        for days in (22, 23):
            make_showtime_for(self.st, days)
        with CaptureQueriesContext(connection) as three:
            html = self.fragment()
        self.assertEqual(html.count(CHIP), 3)
        self.assertEqual(len(three), len(one))
