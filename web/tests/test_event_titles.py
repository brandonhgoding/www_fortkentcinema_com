"""Event suffixes typed into an engagement's title.

Staff mark a Heckle Night by typing it into the event title, and did so two
ways: "Attack of the Giant Leeches (HECKLE NIGHT)" and "The Brain That
Wouldn't Die (Heckle Night)". The home page showed both side by side, and
the Heckle Night page repeated the night's own name after every film.
"""

import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from web.services.cinema_data import get_coming_soon
from web.services.titles import listing_title, split_event_suffix


class SplitEventSuffixTests(SimpleTestCase):
    def test_shouting_suffix(self):
        self.assertEqual(
            split_event_suffix("Attack of the Giant Leeches (HECKLE NIGHT)"),
            ("Attack of the Giant Leeches", "Heckle Night"),
        )

    def test_title_case_suffix(self):
        self.assertEqual(
            split_event_suffix("The Brain That Wouldn't Die (Heckle Night)"),
            ("The Brain That Wouldn't Die", "Heckle Night"),
        )

    def test_craft_night_both_names(self):
        for raw in ("Coraline (craft night)", "Coraline (Craft Cinema Night)"):
            self.assertEqual(split_event_suffix(raw)[0], "Coraline")
        self.assertEqual(
            split_event_suffix("Coraline (craft cinema night)")[1],
            "Craft Cinema Night",
        )

    def test_other_parentheticals_are_part_of_the_title(self):
        for raw in (
            "Spirited Away 25th Anniversary – Studio Ghibli Fest 2026 (Dubbed)",
            "9 (2009)",
            "Heckle Night",
        ):
            self.assertEqual(split_event_suffix(raw), (raw, None))

    def test_tolerates_extra_space(self):
        self.assertEqual(
            split_event_suffix("Leeches  ( heckle night ) "),
            ("Leeches", "Heckle Night"),
        )


class ListingTitleTests(SimpleTestCase):
    def test_normalises_the_suffix(self):
        self.assertEqual(
            listing_title("Attack of the Giant Leeches (HECKLE NIGHT)"),
            "Attack of the Giant Leeches (Heckle Night)",
        )

    def test_leaves_plain_titles_alone(self):
        self.assertEqual(listing_title("Street Fighter"), "Street Fighter")


class EventTitleIntegrationTests(TestCase):
    """The helpers wired into the pages that show engagement titles."""

    def setUp(self):
        self.screen = Screen.objects.create(name="The Savoy", capacity=100)

    def book(self, event_title, date, hour, kind=Engagement.Kind.SPECIAL_EVENT):
        film = Film.objects.create(title="Attack of the Giant Leeches")
        engagement = Engagement.objects.create(
            screen=self.screen, start_date=date, end_date=date,
            status="CONFIRMED", kind=kind, event_title=event_title,
        )
        EngagementFilm.objects.create(engagement=engagement, film=film, position=1)
        Showtime.objects.create(
            engagement=engagement, screen=self.screen,
            starts_at=timezone.make_aware(
                datetime.datetime.combine(date, datetime.time(hour))
            ),
        )

    def test_coming_soon_normalises_the_suffix(self):
        start = timezone.localdate() + datetime.timedelta(days=5)
        self.book("Attack of the Giant Leeches (HECKLE NIGHT)", start, 19)
        titles = [m["title"] for m in get_coming_soon()]
        self.assertEqual(titles, ["Attack of the Giant Leeches (Heckle Night)"])

    def test_the_stored_title_is_untouched(self):
        """The dashboard and social cards still read it as typed."""
        start = timezone.localdate() + datetime.timedelta(days=5)
        self.book("Attack of the Giant Leeches (HECKLE NIGHT)", start, 19)
        self.assertEqual(
            Engagement.objects.get().display_title,
            "Attack of the Giant Leeches (HECKLE NIGHT)",
        )
