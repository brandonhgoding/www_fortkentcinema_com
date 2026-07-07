from unittest import mock

from cinema.tmdb import TMDBAPIError, TMDBClient, TMDBService
from django.core.cache import cache
from django.test import TestCase, override_settings

import requests


@override_settings(TMDB_API_KEY="testkey", TMDB_BASE_URL="https://api.tmdb/3",
                   TMDB_IMAGE_BASE_URL="https://img.tmdb/")
class TMDBClientTests(TestCase):
    def test_requires_key(self) -> None:
        with override_settings(TMDB_API_KEY=""):
            with self.assertRaises(ValueError):
                TMDBClient()

    def test_build_image_url(self) -> None:
        c = TMDBClient()
        self.assertEqual(c.build_image_url(None), "")
        self.assertEqual(c.build_image_url("/p.jpg", size="w500"), "https://img.tmdb/w500/p.jpg")

    @mock.patch("cinema.tmdb.client.requests.get")
    def test_search_movies_ok(self, mget) -> None:
        mget.return_value = mock.Mock(status_code=200,
                                      json=lambda: {"results": [{"id": 1, "title": "A"}]})
        mget.return_value.raise_for_status = lambda: None
        data = TMDBClient().search_movies("a")
        self.assertEqual(data["results"][0]["title"], "A")

    @mock.patch("cinema.tmdb.client.requests.get")
    def test_http_error_becomes_tmdb_error(self, mget) -> None:
        resp = mock.Mock(status_code=401)
        resp.json = lambda: {"status_message": "bad"}
        err = requests.exceptions.HTTPError(response=resp)
        m = mock.Mock()
        m.raise_for_status.side_effect = err
        mget.return_value = m
        with self.assertRaises(TMDBAPIError) as ctx:
            TMDBClient().search_movies("a")
        self.assertEqual(ctx.exception.status_code, 401)


@override_settings(TMDB_API_KEY="testkey", TMDB_BASE_URL="https://api.tmdb/3",
                   TMDB_IMAGE_BASE_URL="https://img.tmdb/")
class TMDBServiceTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    @mock.patch("cinema.tmdb.client.requests.get")
    def test_search_films_normalizes_and_caches(self, mget) -> None:
        payload = {"results": [{"id": 7, "title": "Nope", "release_date": "2022-08-19",
                                "overview": "o", "poster_path": "/p.jpg", "vote_average": 7.5}]}
        m = mock.Mock(json=lambda: payload)
        m.raise_for_status = lambda: None
        mget.return_value = m
        out = TMDBService().search_films("nope")
        self.assertEqual(out[0]["tmdb_id"], 7)
        self.assertEqual(out[0]["poster_path"], "https://img.tmdb/w500/p.jpg")
        self.assertEqual(out[0]["runtime"], None)
        # Second call is cached -> requests.get not called again
        TMDBService().search_films("nope")
        self.assertEqual(mget.call_count, 1)

    @mock.patch("cinema.tmdb.client.requests.get")
    def test_get_film_details(self, mget) -> None:
        payload = {"id": 7, "title": "Nope", "runtime": 130, "imdb_id": "tt1",
                   "genres": [{"name": "Horror"}], "poster_path": "/p.jpg"}
        m = mock.Mock(json=lambda: payload)
        m.raise_for_status = lambda: None
        mget.return_value = m
        d = TMDBService().get_film_details(7)
        self.assertEqual(d["runtime"], 130)
        self.assertEqual(d["genres"], ["Horror"])
        self.assertEqual(d["imdb_id"], "tt1")
