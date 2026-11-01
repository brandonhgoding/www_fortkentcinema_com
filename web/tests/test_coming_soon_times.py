"""Showtimes are listed only in the Now Showing hero (owner, 2026-10-31: not
committing to times for runs further out). A Coming Soon card and a
calendar poster name the run and its dates, never its times, and only the
hero's showings are marked up as ScreeningEvents.
"""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from web.tests.test_home_tickets import (
    CHIP,
    coming_soon_section,
    coming_soon_showtime,
    screening_events,
)


class ComingSoonCardTests(TestCase):
    def setUp(self):
        # A run three weeks out: past the hero's week, so only Coming Soon
        # lists it.
        self.st = coming_soon_showtime(days=21)

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def test_the_card_lists_the_run_but_no_times(self):
        section = coming_soon_section(self.home())
        self.assertIn("Dune", section)
        self.assertNotIn(CHIP, section)

    def test_its_showings_are_not_marked_up(self):
        self.assertIsNone(screening_events(self.home()))

    def test_a_run_in_the_hero_is_marked_up_from_the_hero_only(self):
        # Starts the day after tomorrow: on the hero and on a Coming Soon
        # card. Its one event names the hero.
        coming_soon_showtime(days=2)
        events = screening_events(self.home())
        self.assertEqual(
            [e["offers"]["url"] for e in events], ["http://testserver/#now-showing"]
        )


class CalendarPosterTests(TestCase):
    def test_a_future_days_poster_names_the_run(self):
        coming_soon_showtime(days=21)
        day = timezone.localdate() + datetime.timedelta(days=21)
        response = self.client.get(
            reverse("calendar_month", args=[day.year, day.month - 1])
        )
        (cell,) = [c for c in response.context["cells"] if c["day"] == day.day]
        self.assertEqual([m["title"] for m in cell["movies"]], ["Dune"])
        self.assertContains(response, 'title="Dune"')
