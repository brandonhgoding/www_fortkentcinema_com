from unittest import mock

import requests
from django.core.cache import cache
from django.test import SimpleTestCase

from web.services import leprinceos


def _resp(payload):
    m = mock.Mock()
    m.ok = True
    m.json.return_value = payload
    m.raise_for_status.return_value = None
    return m


class FormatHelpersTests(SimpleTestCase):
    def test_runtime(self):
        self.assertEqual(leprinceos._format_runtime(136), "2h 16min")
        self.assertEqual(leprinceos._format_runtime(60), "1h")
        self.assertEqual(leprinceos._format_runtime(45), "45min")
        self.assertEqual(leprinceos._format_runtime(None), "")

    def test_local_date_and_time_eastern(self):
        # 2025-01-15 00:30 UTC == 2025-01-14 19:30 America/New_York (EST)
        self.assertEqual(leprinceos._local_date("2025-01-15T00:30:00Z"), "2025-01-14")
        self.assertEqual(leprinceos._format_showtime("2025-01-15T00:30:00Z"), "7:30 PM")


class GetNowShowingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_groups_showtimes_by_local_date_and_filters_empty(self):
        engagements = [
            {
                "id": 1,
                "film_title": "Dune",
                "film_poster_url": "d.jpg",
                "films": [{"id": 9}],
                "is_free_for_members": True,
                "show_in_main_listings": True,
            },
        ]
        showtimes = [
            # 18:00Z == 1:00 PM EST — two distinct Eastern dates
            {"id": 100, "starts_at": "2999-01-15T18:00:00Z"},
            {"id": 101, "starts_at": "2999-01-16T18:00:00Z"},
        ]
        film = {"rating": "PG-13", "runtime_minutes": 155, "youtube_id": "abc"}

        def fake_get(url, timeout=None):
            if "/engagements/?" in url:
                return _resp({"results": engagements})
            if "/showtimes/" in url:
                return _resp({"results": showtimes})
            if "/films/9" in url:
                return _resp(film)
            return _resp({"results": []})

        with mock.patch("web.services.leprinceos.requests.get", side_effect=fake_get):
            movies = leprinceos.get_now_showing()

        self.assertEqual(len(movies), 1)
        m = movies[0]
        self.assertEqual(m["id"], "1")
        self.assertEqual(m["title"], "Dune")
        self.assertEqual(m["rating"], "PG-13")
        self.assertEqual(m["runtime"], "2h 35min")
        self.assertEqual(m["youtube_id"], "abc")
        self.assertTrue(m["is_free_for_members"])
        # Two UTC times land on two distinct Eastern dates:
        self.assertEqual(sorted(m["showtimes"].keys()), ["2999-01-15", "2999-01-16"])
        self.assertEqual(
            m["showtimes"]["2999-01-15"], ["1:00 PM"]
        )  # 18:00Z -> 1:00 PM EST

    def test_stale_fallback_on_error(self):
        engagements = [
            {"id": 2, "film_title": "X", "films": [], "show_in_main_listings": True}
        ]
        # Prime the cache via a successful engagements call, then fail.
        ok = _resp({"results": engagements})
        with mock.patch("web.services.leprinceos.requests.get", return_value=ok):
            leprinceos._get("/engagements/?status=CONFIRMED")
        boom = mock.Mock(side_effect=RuntimeError("down"))
        with mock.patch("web.services.leprinceos.requests.get", side_effect=boom):
            # After TTL, a failed refetch serves last-good instead of raising.
            cache.delete(
                "lpos:/engagements/?status=CONFIRMED"
            )  # expire fresh, keep stale
            data = leprinceos._get("/engagements/?status=CONFIRMED")
        self.assertEqual(data, engagements)

    def test_non_ok_status_falls_back_to_stale(self):
        # Prime the stale cache via a successful call.
        engagements = [
            {"id": 7, "film_title": "Y", "films": [], "show_in_main_listings": True}
        ]
        ok = _resp({"results": engagements})
        with mock.patch("web.services.leprinceos.requests.get", return_value=ok):
            leprinceos._get("/engagements/?x=1")
        # Expire the fresh key but keep the stale copy.
        cache.delete("lpos:/engagements/?x=1")
        # A non-2xx response that still returns a JSON body (e.g. a DRF error
        # payload) must not be treated as a successful fetch: raise_for_status
        # should raise, triggering the stale fallback instead of caching/
        # returning the error dict.
        bad = mock.Mock()
        bad.json.return_value = {"detail": "boom"}
        bad.raise_for_status.side_effect = requests.HTTPError("500")
        with mock.patch("web.services.leprinceos.requests.get", return_value=bad):
            data = leprinceos._get("/engagements/?x=1")
        self.assertEqual(data, engagements)


class GetComingSoonTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_dedups_by_film_set_and_excludes_classics(self):
        engagements = [
            {
                "id": 10,
                "film_title": "Dune Part Two",
                "start_date": "2999-02-01",
                "films": [{"id": 5, "title": "Dune Part Two", "poster_url": "p.jpg"}],
                "film_poster_url": "d2.jpg",
                "is_free_for_members": False,
                "kind": "REGULAR",
            },
            {
                # Same film set as above -> should be deduped out
                "id": 11,
                "film_title": "Dune Part Two",
                "start_date": "2999-02-05",
                "films": [{"id": 5, "title": "Dune Part Two", "poster_url": "p.jpg"}],
                "film_poster_url": "d2.jpg",
                "is_free_for_members": False,
                "kind": "REGULAR",
            },
            {
                # Classic screening -> excluded
                "id": 12,
                "film_title": "Casablanca",
                "start_date": "2999-02-10",
                "films": [],
                "kind": "CLASSIC",
            },
        ]
        film = {"synopsis": "Desert politics.", "youtube_id": "xyz"}

        def fake_get(url, timeout=None):
            if "/engagements/?" in url:
                return _resp({"results": engagements})
            if "/films/5" in url:
                return _resp(film)
            return _resp({"results": []})

        with mock.patch("web.services.leprinceos.requests.get", side_effect=fake_get):
            movies = leprinceos.get_coming_soon()

        self.assertEqual(len(movies), 1)
        m = movies[0]
        self.assertEqual(m["id"], "10")
        self.assertEqual(m["title"], "Dune Part Two")
        self.assertEqual(m["start_date"], "2999-02-01")
        self.assertEqual(m["release_date"], "February 1")
        self.assertEqual(m["description"], "Desert politics.")
        self.assertEqual(m["youtube_id"], "xyz")
        self.assertFalse(m["is_free_for_members"])
        self.assertEqual(
            m["films"], [{"id": 5, "title": "Dune Part Two", "poster": "p.jpg"}]
        )
