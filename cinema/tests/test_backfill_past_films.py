from datetime import date, datetime

from cinema.management.commands import backfill_past_films as cmd
from cinema.models import Engagement, Screen
from django.test import TestCase
from django.utils import timezone


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


class FindFreeSlotTests(TestCase):
    def setUp(self) -> None:
        self.a = Screen.objects.create(name="The Century", capacity=1)
        self.b = Screen.objects.create(name="The Savoy", capacity=1)
        self.screens = [self.a, self.b]

    def _at(self, hour: int) -> datetime:
        return timezone.make_aware(datetime(2024, 1, 1, hour, 0))

    def test_prefers_3pm_on_preferred_screen(self) -> None:
        screen, when = cmd.find_free_slot(set(), date(2024, 1, 1), self.screens, 0)
        self.assertEqual(screen, self.a)
        self.assertEqual(when, self._at(15))

    def test_rotates_preferred_screen(self) -> None:
        screen, when = cmd.find_free_slot(set(), date(2024, 1, 1), self.screens, 1)
        self.assertEqual(screen, self.b)
        self.assertEqual(when, self._at(15))

    def test_falls_back_to_other_screen_at_same_hour(self) -> None:
        taken = {(self.a.id, self._at(15))}
        screen, when = cmd.find_free_slot(taken, date(2024, 1, 1), self.screens, 0)
        self.assertEqual(screen, self.b)
        self.assertEqual(when, self._at(15))

    def test_falls_back_to_later_hour_when_both_screens_taken(self) -> None:
        taken = {(self.a.id, self._at(15)), (self.b.id, self._at(15))}
        screen, when = cmd.find_free_slot(taken, date(2024, 1, 1), self.screens, 0)
        self.assertEqual(screen, self.a)
        self.assertEqual(when, self._at(16))
