"""The home hero's featured showing: the next showing that has not started.

Same pool as Now Showing (confirmed, listed, within the week), so the hero
never names a film the listings below it do not.
"""

import datetime

from cinema.models import Showtime
from django.test import TestCase
from django.utils import timezone

from web.services.cinema_data import get_featured_showtime
from web.tests.test_cinema_data import aware, make_engagement, make_film, make_screen


class FeaturedShowtimeTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.today = timezone.localdate()
        self.film = make_film(
            "Hocus Pocus",
            runtime_minutes=96,
            rating="PG",
            overview="Three witches are back.",
            poster_url="https://image.tmdb.org/t/p/w500/poster.jpg",
            backdrop_url="https://image.tmdb.org/t/p/w780/back.jpg",
        )
        self.eng = make_engagement(
            self.screen, [self.film],
            start=self.today, end=self.today + datetime.timedelta(days=3),
        )

    def at(self, days, hour, minute=0):
        d = self.today + datetime.timedelta(days=days)
        return aware(d.year, d.month, d.day, hour, minute)

    def show(self, days, hour, eng=None, **kw):
        return Showtime.objects.create(
            engagement=eng or self.eng, screen=self.screen,
            starts_at=self.at(days, hour), **kw,
        )

    def test_describes_the_next_showing(self) -> None:
        st = self.show(1, 19)
        out = get_featured_showtime(now=self.at(0, 12))
        self.assertEqual(out["showtime_id"], st.pk)
        self.assertEqual(out["title"], "Hocus Pocus")
        self.assertEqual(out["rating"], "PG")
        self.assertEqual(out["runtime"], "1h 36min")
        self.assertEqual(out["description"], "Three witches are back.")
        self.assertEqual(out["poster"], "https://image.tmdb.org/t/p/w500/poster.jpg")
        tomorrow = self.today + datetime.timedelta(days=1)
        self.assertEqual(out["date"], tomorrow.isoformat())
        self.assertEqual(out["time"], "7:00 PM")

    def test_backdrop_is_asked_for_at_hero_width(self) -> None:
        # TMDB stores the w780 cut; a 1400px-wide fold wants w1280. Any other
        # host's URL is left alone.
        self.show(1, 19)
        out = get_featured_showtime(now=self.at(0, 12))
        self.assertEqual(out["backdrop"], "https://image.tmdb.org/t/p/w1280/back.jpg")
        self.film.backdrop_url = "https://example.org/still.jpg"
        self.film.save()
        out = get_featured_showtime(now=self.at(0, 12))
        self.assertEqual(out["backdrop"], "https://example.org/still.jpg")

    def test_earliest_upcoming_wins(self) -> None:
        self.show(2, 19)
        tonight = self.show(0, 19)
        self.show(0, 14)  # already started by 3 PM
        out = get_featured_showtime(now=self.at(0, 15))
        self.assertEqual(out["showtime_id"], tonight.pk)

    def test_cancelled_showing_is_skipped(self) -> None:
        self.show(0, 19, is_cancelled=True)
        later = self.show(1, 19)
        out = get_featured_showtime(now=self.at(0, 12))
        self.assertEqual(out["showtime_id"], later.pk)

    def test_unlisted_runs_are_skipped(self) -> None:
        hidden = make_engagement(
            self.screen, [make_film("Private")],
            start=self.today, end=self.today, show=False,
        )
        draft = make_engagement(
            self.screen, [make_film("Draft")],
            start=self.today, end=self.today, status="DRAFT",
        )
        self.show(0, 17, eng=hidden)
        self.show(0, 18, eng=draft)
        listed = self.show(0, 19)
        out = get_featured_showtime(now=self.at(0, 12))
        self.assertEqual(out["showtime_id"], listed.pk)

    def test_beyond_the_week_is_not_featured(self) -> None:
        far = make_engagement(
            self.screen, [make_film("Later")],
            start=self.today + datetime.timedelta(days=8),
            end=self.today + datetime.timedelta(days=9),
        )
        self.show(8, 19, eng=far)
        self.assertIsNone(get_featured_showtime(now=self.at(0, 12)))

    def test_nothing_booked_is_none(self) -> None:
        self.assertIsNone(get_featured_showtime(now=self.at(0, 12)))

    def test_event_title_names_the_night(self) -> None:
        self.eng.display_title = "Hocus Pocus (heckle night)"
        self.eng.save()
        self.show(1, 19)
        out = get_featured_showtime(now=self.at(0, 12))
        self.assertEqual(out["title"], "Hocus Pocus (Heckle Night)")
