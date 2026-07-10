import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.test import TestCase
from django.utils import timezone

from web.services.cinema_data import (
    CINEMA_TZ,
    _format_runtime,
    get_now_showing,
)


def make_screen():
    return Screen.objects.create(name="Screen 1", capacity=100)


def make_film(title="Dune", **kw):
    return Film.objects.create(title=title, **kw)


def make_engagement(screen, films, *, start, end, status="CONFIRMED", kind="REGULAR",
                    show=True, event_title=""):
    eng = Engagement.objects.create(
        screen=screen, start_date=start, end_date=end, status=status, kind=kind,
        show_in_main_listings=show, event_title=event_title,
    )
    for i, f in enumerate(films, start=1):
        EngagementFilm.objects.create(engagement=eng, film=f, position=i)
    return eng


def aware(y, mo, d, hh, mm=0):
    return timezone.make_aware(datetime.datetime(y, mo, d, hh, mm))


class FormatRuntimeTests(TestCase):
    def test_format(self) -> None:
        self.assertEqual(_format_runtime(None), "")
        self.assertEqual(_format_runtime(0), "")
        self.assertEqual(_format_runtime(40), "40min")
        self.assertEqual(_format_runtime(60), "1h")
        self.assertEqual(_format_runtime(100), "1h 40min")


class NowShowingTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.film = make_film("Dune", runtime_minutes=155, rating="PG-13",
                              poster_url="http://p/d.jpg", youtube_id="yt1")
        self.today = timezone.localdate()

    def test_active_engagement_grouped_by_date(self) -> None:
        eng = make_engagement(self.screen, [self.film],
                              start=self.today, end=self.today + datetime.timedelta(days=3))
        d = self.today
        Showtime.objects.create(engagement=eng, starts_at=aware(d.year, d.month, d.day, 13, 0))
        Showtime.objects.create(engagement=eng, starts_at=aware(d.year, d.month, d.day, 19, 0))
        d2 = self.today + datetime.timedelta(days=1)
        Showtime.objects.create(engagement=eng, starts_at=aware(d2.year, d2.month, d2.day, 19, 0))
        out = get_now_showing()
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertEqual(m["title"], "Dune")
        self.assertEqual(m["rating"], "PG-13")
        self.assertEqual(m["runtime"], "2h 35min")
        self.assertEqual(m["genre"], "")
        self.assertEqual(m["poster"], "http://p/d.jpg")
        self.assertEqual(m["youtube_id"], "yt1")
        self.assertEqual(sorted(m["showtimes"].keys()), [d.isoformat(), d2.isoformat()])
        self.assertEqual(m["showtimes"][d.isoformat()], ["1:00 PM", "7:00 PM"])

    def test_hidden_engagement_excluded(self) -> None:
        eng = make_engagement(self.screen, [self.film],
                              start=self.today, end=self.today + datetime.timedelta(days=3), show=False)
        Showtime.objects.create(engagement=eng, starts_at=aware(self.today.year, self.today.month, self.today.day, 19, 0))
        self.assertEqual(get_now_showing(), [])

    def test_out_of_window_excluded(self) -> None:
        far = self.today + datetime.timedelta(days=30)
        eng = make_engagement(self.screen, [self.film], start=far, end=far + datetime.timedelta(days=2))
        Showtime.objects.create(engagement=eng, starts_at=aware(far.year, far.month, far.day, 19, 0))
        self.assertEqual(get_now_showing(), [])

    def test_only_cancelled_showtimes_dropped(self) -> None:
        eng = make_engagement(self.screen, [self.film],
                              start=self.today, end=self.today + datetime.timedelta(days=3))
        Showtime.objects.create(engagement=eng,
                                starts_at=aware(self.today.year, self.today.month, self.today.day, 19, 0),
                                is_cancelled=True)
        self.assertEqual(get_now_showing(), [])

    def test_free_for_members_flag(self) -> None:
        eng = make_engagement(self.screen, [self.film],
                              start=self.today, end=self.today + datetime.timedelta(days=3),
                              kind="CLASSIC")  # CLASSIC is free for members
        Showtime.objects.create(engagement=eng, starts_at=aware(self.today.year, self.today.month, self.today.day, 19, 0))
        out = get_now_showing()
        self.assertTrue(out[0]["is_free_for_members"])


from web.services.cinema_data import get_coming_soon


class ComingSoonTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.today = timezone.localdate()
        self.a = make_film("Alpha", runtime_minutes=90, synopsis="a-syn",
                           poster_url="http://p/a.jpg", youtube_id="yta")
        self.b = make_film("Beta", runtime_minutes=100, poster_url="http://p/b.jpg")

    def _future(self, films, days=3, **kw):
        s = self.today + datetime.timedelta(days=days)
        return make_engagement(self.screen, films, start=s, end=s + datetime.timedelta(days=2), **kw)

    def test_future_non_classic_returned(self) -> None:
        self._future([self.a])
        out = get_coming_soon()
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertEqual(m["title"], "Alpha")
        self.assertEqual(m["genre"], "")
        self.assertEqual(m["poster"], "http://p/a.jpg")
        self.assertEqual(m["description"], "a-syn")
        self.assertEqual(m["youtube_id"], "yta")
        self.assertEqual(m["films"], [{"id": self.a.id, "title": "Alpha", "poster": "http://p/a.jpg"}])
        self.assertEqual(m["start_date"], (self.today + datetime.timedelta(days=3)).isoformat())

    def test_classic_excluded(self) -> None:
        self._future([self.a], kind="CLASSIC")
        self.assertEqual(get_coming_soon(), [])

    def test_dedup_by_film_set(self) -> None:
        self._future([self.a], days=3)
        self._future([self.a], days=5)   # same film -> deduped
        self._future([self.a, self.b], days=6, kind="DOUBLE_FEATURE")  # distinct set -> kept
        titles = sorted(m["title"] for m in get_coming_soon())
        self.assertEqual(len(get_coming_soon()), 2)

    def test_release_date_format(self) -> None:
        s = self.today + datetime.timedelta(days=3)
        self._future([self.a], days=3)
        expected = s.strftime("%B %-d")
        self.assertEqual(get_coming_soon()[0]["release_date"], expected)
