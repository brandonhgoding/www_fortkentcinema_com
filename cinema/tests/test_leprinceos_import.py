import datetime
from io import StringIO
from unittest import mock

from cinema.leprinceos_import import fetch_all, import_all
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class FetchAllTests(TestCase):
    def test_follows_pagination(self) -> None:
        page1 = {"results": [{"id": 1}, {"id": 2}], "next": "https://api/x/?page=2"}
        page2 = {"results": [{"id": 3}], "next": None}
        session = mock.Mock()
        session.get.side_effect = [_Resp(page1), _Resp(page2)]
        out = fetch_all("https://api/x", "/films/", session=session)
        self.assertEqual([r["id"] for r in out], [1, 2, 3])
        # first call hits base+path, second follows the absolute `next` url
        first_url = session.get.call_args_list[0].args[0]
        second_url = session.get.call_args_list[1].args[0]
        self.assertEqual(first_url, "https://api/x/films/")
        self.assertEqual(second_url, "https://api/x/?page=2")

    def test_unwraps_plain_list(self) -> None:
        session = mock.Mock()
        session.get.side_effect = [_Resp([{"id": 9}])]
        out = fetch_all("https://api/x", "/films/", session=session)
        self.assertEqual(out, [{"id": 9}])


FILMS = [
    {"id": 10, "title": "Alpha", "runtime_minutes": 90, "rating": "PG", "synopsis": "s",
     "poster_url": "http://p/a.jpg", "backdrop_url": "", "overview": "", "tmdb_id": None,
     "imdb_id": "tt10", "youtube_id": None},
    {"id": 11, "title": "Beta", "runtime_minutes": 100, "rating": "R", "synopsis": "",
     "poster_url": "", "backdrop_url": "", "overview": "", "tmdb_id": "", "imdb_id": "",
     "youtube_id": ""},
]
ENGAGEMENTS = [
    {"id": 20, "kind": "REGULAR", "event_title": "", "screen": 1, "screen_name": "The Century",
     "start_date": "2026-02-01", "end_date": "2026-02-07", "presentation_format": "2d",
     "status": "CONFIRMED", "show_in_main_listings": True, "notes": "hi",
     "films": [{"id": 10, "title": "Alpha", "poster_url": "http://p/a.jpg", "runtime_minutes": 90}]},
    {"id": 21, "kind": "DOUBLE_FEATURE", "event_title": "Creature Night", "screen": 2,
     "screen_name": "The Savoy", "start_date": "2026-03-01", "end_date": "2026-03-02",
     "presentation_format": "2d", "status": "CONFIRMED", "show_in_main_listings": False, "notes": "",
     "films": [{"id": 11, "title": "Beta"}, {"id": 10, "title": "Alpha"}]},
]
SHOWTIMES = [
    {"id": 30, "engagement": 20, "screen": 1, "screen_name": "The Century",
     "starts_at": "2026-02-01T19:30:00-05:00", "is_cancelled": False, "captions": "CC"},
    {"id": 31, "engagement": 21, "screen": 2, "screen_name": "The Savoy",
     "starts_at": "2026-03-01T20:00:00-05:00", "is_cancelled": True, "captions": None},
]


def _fake_fetch(base_url, path, *, session=None):
    return {"/films/": FILMS, "/engagements/": ENGAGEMENTS, "/showtimes/": SHOWTIMES}[path]


class ImportAllTests(TestCase):
    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_counts_and_rows(self, _f) -> None:
        counts = import_all("http://api", flush=True)
        self.assertEqual(counts["films"], 2)
        self.assertEqual(counts["screens"], 2)          # reconstructed: id 1 + id 2
        self.assertEqual(counts["engagements"], 2)
        self.assertEqual(counts["engagement_films"], 3)  # 1 + 2
        self.assertEqual(counts["showtimes"], 2)
        self.assertEqual(Screen.objects.count(), 2)
        self.assertEqual({s.name for s in Screen.objects.all()}, {"The Century", "The Savoy"})
        self.assertTrue(all(s.capacity == 1 for s in Screen.objects.all()))

    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_empty_external_ids_nulled(self, _f) -> None:
        import_all("http://api", flush=True)
        beta = Film.objects.get(title="Beta")
        self.assertIsNone(beta.tmdb_id)
        self.assertIsNone(beta.imdb_id)

    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_double_feature_ordering(self, _f) -> None:
        import_all("http://api", flush=True)
        eng = Engagement.objects.get(event_title="Creature Night")
        pairs = list(eng.engagement_films.values_list("film__title", "position"))
        self.assertEqual(pairs, [("Beta", 1), ("Alpha", 2)])

    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_showtime_tz_aware(self, _f) -> None:
        import_all("http://api", flush=True)
        st = Showtime.objects.get(is_cancelled=False)
        self.assertIsNotNone(st.starts_at.tzinfo)
        # 2026-02-01T19:30:00-05:00 == 2026-02-02T00:30:00Z
        self.assertEqual(st.starts_at.astimezone(datetime.timezone.utc).isoformat(),
                         "2026-02-02T00:30:00+00:00")

    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_flush_clears_prior_rows(self, _f) -> None:
        Screen.objects.create(name="Junk", capacity=5)
        import_all("http://api", flush=True)
        self.assertFalse(Screen.objects.filter(name="Junk").exists())

    def test_requires_flush(self) -> None:
        with self.assertRaises(ValueError):
            import_all("http://api", flush=False)
        self.assertEqual(Screen.objects.count(), 0)  # nothing written


class CommandTests(TestCase):
    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_command_with_flush_imports(self, _f) -> None:
        out = StringIO()
        call_command("import_leprinceos", "--flush", "--base-url", "http://api", stdout=out)
        self.assertEqual(Film.objects.count(), 2)
        self.assertIn("films", out.getvalue().lower())

    def test_command_without_flush_writes_nothing(self) -> None:
        with self.assertRaises(CommandError):
            call_command("import_leprinceos", "--base-url", "http://api")
        self.assertEqual(Film.objects.count(), 0)
