import datetime
from importlib import import_module

from cinema.models import Engagement, Screen
from django.apps import apps
from django.test import TestCase

MIGRATION = import_module("cinema.migrations.0025_special_event_to_regular")
NIGHT = datetime.date(2026, 10, 16)


class SpecialEventToRegularTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="S", capacity=10)

    def _row(self, kind, title=""):
        return Engagement.objects.create(
            screen=self.screen, start_date=NIGHT, end_date=NIGHT,
            kind=kind, display_title=title,
        )

    def test_special_event_rows_become_regular_and_keep_their_title(self) -> None:
        event = self._row("SPECIAL_EVENT", "Heckle Night")
        classic = self._row("CLASSIC", "Noir Night")
        MIGRATION.special_event_to_regular(apps, None)
        event.refresh_from_db()
        classic.refresh_from_db()
        self.assertEqual((event.kind, event.display_title), ("REGULAR", "Heckle Night"))
        self.assertEqual((classic.kind, classic.display_title), ("CLASSIC", "Noir Night"))
