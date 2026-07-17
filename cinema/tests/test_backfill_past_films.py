from datetime import date

from cinema.management.commands import backfill_past_films as cmd
from cinema.models import Engagement
from django.test import TestCase


class HelperTests(TestCase):
    def test_regular_film_kind(self) -> None:
        entry = {"type": "Film", "notes": ""}
        self.assertEqual(cmd.engagement_kind(entry), Engagement.Kind.REGULAR)

    def test_special_classic_kind(self) -> None:
        entry = {"type": "Special screening", "notes": "Classic re-release"}
        self.assertEqual(cmd.engagement_kind(entry), Engagement.Kind.CLASSIC)

    def test_special_event_kind(self) -> None:
        entry = {"type": "Special screening", "notes": "Interactive event screening"}
        self.assertEqual(cmd.engagement_kind(entry), Engagement.Kind.SPECIAL_EVENT)

    def test_daterange_is_inclusive(self) -> None:
        days = list(cmd.daterange(date(2024, 1, 1), date(2024, 1, 3)))
        self.assertEqual(days, [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)])

    def test_films_dataset_loaded(self) -> None:
        self.assertEqual(len(cmd.FILMS), 90)
        self.assertEqual(cmd.FILMS[0]["title"], "Despicable Me 4")
