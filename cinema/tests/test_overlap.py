import datetime
from zoneinfo import ZoneInfo

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from cinema.showtimes_overlap import (
    _ProposedShowtime,
    check_intra_batch_overlaps,
    check_overlap_against_existing,
    format_overlap_error,
    get_effective_end,
)
from django.test import TestCase

TZ = ZoneInfo("America/New_York")


def _dt(y, m, d, hh, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=TZ)


class OverlapServiceTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.eng = Engagement.objects.create(
            screen=self.screen, start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 31),
        )
        EngagementFilm.objects.create(engagement=self.eng, film=self.film, position=1)

    def test_effective_end_uses_runtime_and_buffer(self) -> None:
        end = get_effective_end(_dt(2026, 7, 4, 19), 100)
        self.assertEqual(end, _dt(2026, 7, 4, 19) + datetime.timedelta(minutes=130))

    def test_effective_end_defaults_when_no_runtime(self) -> None:
        end = get_effective_end(_dt(2026, 7, 4, 19), None)
        self.assertEqual(end, _dt(2026, 7, 4, 19) + datetime.timedelta(minutes=180))

    def test_overlap_against_existing_detected(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19))
        # 155 min + 30 buffer = 185 min -> ends ~22:05; a 21:00 start overlaps
        conflicts = check_overlap_against_existing(
            self.screen, _dt(2026, 7, 4, 21), 155, "Dune")
        self.assertEqual(len(conflicts), 1)

    def test_no_overlap_when_after_effective_end(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19))
        conflicts = check_overlap_against_existing(
            self.screen, _dt(2026, 7, 4, 23), 155, "Dune")
        self.assertEqual(conflicts, [])

    def test_cancelled_excluded(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19), is_cancelled=True)
        conflicts = check_overlap_against_existing(
            self.screen, _dt(2026, 7, 4, 20), 155, "Dune")
        self.assertEqual(conflicts, [])

    def test_exclude_self(self) -> None:
        st = Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19))
        conflicts = check_overlap_against_existing(
            self.screen, _dt(2026, 7, 4, 19), 155, "Dune", exclude_showtime_id=st.pk)
        self.assertEqual(conflicts, [])

    def test_intra_batch_overlap(self) -> None:
        proposed = [
            _ProposedShowtime(0, self.screen, _dt(2026, 7, 4, 19), 155, "Dune"),
            _ProposedShowtime(1, self.screen, _dt(2026, 7, 4, 20), 155, "Dune"),
        ]
        conflicts = check_intra_batch_overlaps(proposed)
        self.assertEqual(len(conflicts), 1)

    def test_format_error_strings(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19))
        c = check_overlap_against_existing(self.screen, _dt(2026, 7, 4, 20), 155, "Dune")[0]
        msg = format_overlap_error(c)
        self.assertIn("overlaps with", msg)
        self.assertIn("Screen 1", msg)
