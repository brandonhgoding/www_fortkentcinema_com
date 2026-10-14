import datetime

from cinema.models import (
    Engagement,
    EngagementFilm,
    EngagementStatus,
    Film,
    Language,
    Screen,
    Showtime,
    Translation,
)
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone as dj_timezone


class FilmTestCase(TestCase):
    def test_str_is_title(self) -> None:
        film = Film.objects.create(title="Toy Story 5")
        self.assertEqual(str(film), "Toy Story 5")

    def test_blank_external_ids_coerced_to_none(self) -> None:
        # Empty-string ids must become NULL so multiple blank films are allowed
        # under the unique constraints on tmdb_id/imdb_id/youtube_id.
        first = Film.objects.create(title="A", tmdb_id="", imdb_id="", youtube_id="")
        second = Film.objects.create(title="B", tmdb_id="", imdb_id="", youtube_id="")
        first.refresh_from_db()
        self.assertIsNone(first.tmdb_id)
        self.assertIsNone(second.tmdb_id)


class ScreenTestCase(TestCase):
    def test_str_is_name(self) -> None:
        screen = Screen.objects.create(name="Screen 1", capacity=120)
        self.assertEqual(str(screen), "Screen 1")

    def test_defaults(self) -> None:
        screen = Screen.objects.create(name="Main", capacity=200)
        self.assertEqual(screen.screen_type, "standard")
        self.assertEqual(screen.aspect_ratio, "scope")
        self.assertEqual(screen.sound_system, "standard")
        self.assertFalse(screen.supports_3d)


class EngagementTestCase(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film_a = Film.objects.create(title="Alpha", runtime_minutes=90)
        self.film_b = Film.objects.create(title="Beta", runtime_minutes=100)

    def _engagement(self, **kwargs) -> Engagement:
        defaults = dict(
            screen=self.screen,
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
        )
        defaults.update(kwargs)
        return Engagement.objects.create(**defaults)

    def test_title_from_films_in_position_order(self) -> None:
        eng = self._engagement()
        EngagementFilm.objects.create(engagement=eng, film=self.film_b, position=2)
        EngagementFilm.objects.create(engagement=eng, film=self.film_a, position=1)
        self.assertEqual(eng.title, "Alpha + Beta")
        self.assertEqual([f.title for f in eng.ordered_films], ["Alpha", "Beta"])
        self.assertEqual(eng.primary_film, self.film_a)
        self.assertEqual(eng.total_runtime_minutes, 190)

    def test_language_defaults_to_english(self) -> None:
        eng = self._engagement()
        self.assertEqual(eng.language, Language.ENGLISH)
        self.assertEqual(eng.language, "english")
        self.assertEqual(eng.get_language_display(), "English")

    def test_translation_defaults_to_none(self) -> None:
        self.assertEqual(self._engagement().translation, Translation.NONE)

    def test_english_film_cannot_be_translated(self) -> None:
        eng = self._engagement(translation=Translation.DUBBED)
        with self.assertRaises(ValidationError) as ctx:
            eng.full_clean()
        self.assertIn("translation", ctx.exception.message_dict)

    def test_non_english_film_can_be_translated(self) -> None:
        eng = self._engagement(
            language=Language.FRENCH, translation=Translation.DUBBED
        )
        eng.full_clean()

    def test_display_title_overrides_the_film_titles(self) -> None:
        eng = self._engagement(display_title="Summer Double Feature")
        self.assertEqual(eng.title, "Summer Double Feature")

    def test_title_is_empty_with_no_films_and_no_override(self) -> None:
        self.assertEqual(self._engagement().title, "")

    def test_special_event_is_no_longer_a_kind(self) -> None:
        self.assertEqual(
            Engagement.Kind.values, ["REGULAR", "CLASSIC", "DOUBLE_FEATURE"]
        )
        self.assertFalse(hasattr(Engagement, "default_visibility_for"))

    def test_clean_rejects_end_before_start(self) -> None:
        eng = Engagement(
            screen=self.screen,
            start_date=datetime.date(2026, 7, 7),
            end_date=datetime.date(2026, 7, 1),
        )
        with self.assertRaises(ValidationError):
            eng.clean()

    def test_unique_engagement_position(self) -> None:
        eng = self._engagement()
        EngagementFilm.objects.create(engagement=eng, film=self.film_a, position=1)
        # Wrap the failing INSERT in atomic() so the broken transaction is
        # contained and TestCase teardown can still roll back cleanly.
        with self.assertRaises(IntegrityError), transaction.atomic():
            EngagementFilm.objects.create(engagement=eng, film=self.film_b, position=1)

    def test_is_free_for_members_defaults_off(self) -> None:
        for kind in (Engagement.Kind.CLASSIC, Engagement.Kind.REGULAR):
            self.assertFalse(self._engagement(kind=kind).is_free_for_members)

    def test_is_free_for_members_when_set(self) -> None:
        eng = self._engagement(kind=Engagement.Kind.REGULAR)
        eng.is_free_for_members = True
        eng.save(update_fields=["is_free_for_members"])
        eng.refresh_from_db()
        self.assertTrue(eng.is_free_for_members)


class ShowtimeTestCase(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.other_screen = Screen.objects.create(name="Screen 2", capacity=80)
        self.film = Film.objects.create(title="Alpha", runtime_minutes=90)
        self.eng = Engagement.objects.create(
            screen=self.screen,
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
        )
        EngagementFilm.objects.create(engagement=self.eng, film=self.film, position=1)

    def _dt(self, day: int, hour: int) -> datetime.datetime:
        return dj_timezone.make_aware(datetime.datetime(2026, 7, day, hour, 0))

    def test_save_defaults_screen_from_engagement(self) -> None:
        showtime = Showtime(engagement=self.eng, starts_at=self._dt(2, 19))
        showtime.save()
        self.assertEqual(showtime.screen_id, self.screen.id)

    def test_save_keeps_explicit_screen(self) -> None:
        showtime = Showtime.objects.create(
            engagement=self.eng, screen=self.other_screen, starts_at=self._dt(2, 19)
        )
        self.assertEqual(showtime.screen_id, self.other_screen.id)

    def test_unique_screen_starts_at(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=self._dt(2, 19))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Showtime.objects.create(engagement=self.eng, starts_at=self._dt(2, 19))

    def test_cancelled_showtime_frees_its_slot(self) -> None:
        Showtime.objects.create(
            engagement=self.eng, starts_at=self._dt(2, 19), is_cancelled=True
        )
        Showtime.objects.create(engagement=self.eng, starts_at=self._dt(2, 19))
        self.assertEqual(Showtime.objects.count(), 2)


class EngagementCancellationTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        today = dj_timezone.localdate()
        self.eng = Engagement.objects.create(
            screen=self.screen,
            start_date=today - datetime.timedelta(days=3),
            end_date=today + datetime.timedelta(days=3),
            status=EngagementStatus.CONFIRMED,
        )
        now = dj_timezone.now()
        self.past = Showtime.objects.create(
            engagement=self.eng, starts_at=now - datetime.timedelta(days=1)
        )
        self.upcoming = Showtime.objects.create(
            engagement=self.eng, starts_at=now + datetime.timedelta(days=1)
        )

    def test_cancelling_the_run_cancels_its_upcoming_showtimes(self) -> None:
        self.eng.status = EngagementStatus.CANCELLED
        self.eng.save(update_fields=["status"])
        self.upcoming.refresh_from_db()
        self.past.refresh_from_db()
        self.assertTrue(self.upcoming.is_cancelled)
        self.assertFalse(self.past.is_cancelled)

    def test_other_statuses_leave_showtimes_alone(self) -> None:
        self.eng.status = EngagementStatus.DRAFT
        self.eng.save()
        self.upcoming.refresh_from_db()
        self.assertFalse(self.upcoming.is_cancelled)

    def test_resaving_a_cancelled_run_keeps_re_enabled_showtimes(self) -> None:
        self.eng.status = EngagementStatus.CANCELLED
        self.eng.save()
        self.upcoming.refresh_from_db()
        self.upcoming.is_cancelled = False
        self.upcoming.save()
        self.eng.notes = "Typo fixed"
        self.eng.save()
        self.upcoming.refresh_from_db()
        self.assertFalse(self.upcoming.is_cancelled)

    def test_freed_slot_can_be_rebooked(self) -> None:
        self.eng.status = EngagementStatus.CANCELLED
        self.eng.save()
        Showtime.objects.create(
            engagement=self.eng, starts_at=self.upcoming.starts_at
        )


class EngagementAdmissionsTests(TestCase):
    def test_admissions_defaults_to_none_and_stores_count(self) -> None:
        screen = Screen.objects.create(name="The Century", capacity=1)
        eng = Engagement.objects.create(
            screen=screen, start_date=datetime.date(2024, 1, 1), end_date=datetime.date(2024, 1, 3)
        )
        self.assertIsNone(eng.admissions)  # unknown by default
        eng.admissions = 472
        eng.save()
        eng.refresh_from_db()
        self.assertEqual(eng.admissions, 472)


class InTicketReportTests(TestCase):
    def test_defaults_true(self) -> None:
        screen = Screen.objects.create(name="S", capacity=10)
        day = datetime.date(2026, 10, 9)
        eng = Engagement.objects.create(screen=screen, start_date=day, end_date=day)
        self.assertTrue(eng.in_ticket_report)
