import datetime

from cinema.models import Engagement, Screen, Showtime
from django.test import TestCase
from django.utils import timezone

from web.constants import (
    TICKET_CUTOFF_MINUTES,
    TICKET_HOLD_MINUTES,
    TICKET_ONLINE_SHARE,
)


def aware(*args: int) -> datetime.datetime:
    return timezone.make_aware(datetime.datetime(*args))


class EffectiveAllowanceTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="S1", capacity=101)
        eng = Engagement.objects.create(
            screen=self.screen,
            start_date=datetime.date(2026, 10, 20),
            end_date=datetime.date(2026, 10, 26),
            status="CONFIRMED",
        )
        self.st = Showtime.objects.create(
            engagement=eng, starts_at=aware(2026, 10, 20, 19)
        )

    def test_default_is_half_the_seats_rounded_down(self) -> None:
        self.assertEqual(self.st.effective_online_allowance, 50)

    def test_override_wins(self) -> None:
        self.st.online_allowance = 7
        self.assertEqual(self.st.effective_online_allowance, 7)

    def test_zero_override_means_none_online(self) -> None:
        self.st.online_allowance = 0
        self.assertEqual(self.st.effective_online_allowance, 0)

    def test_constants(self) -> None:
        self.assertEqual(
            (TICKET_ONLINE_SHARE, TICKET_HOLD_MINUTES, TICKET_CUTOFF_MINUTES),
            (0.5, 20, 30),
        )
