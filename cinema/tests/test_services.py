from unittest import mock

from cinema.models import Film
from cinema.services import import_film_from_tmdb
from django.test import TestCase

DETAILS = {
    "tmdb_id": 42, "title": "The Answer", "release_date": "2001-01-01",
    "overview": "o", "poster_path": "https://img/x.jpg", "backdrop_path": "https://img/b.jpg",
    "runtime": 108, "genres": ["Sci-Fi"], "imdb_id": "tt42",
}


class ImportFilmFromTMDBTests(TestCase):
    def test_creates_film(self) -> None:
        svc = mock.Mock()
        svc.get_film_details.return_value = DETAILS
        film = import_film_from_tmdb(42, service=svc)
        self.assertEqual(film.title, "The Answer")
        self.assertEqual(film.tmdb_id, "42")
        self.assertEqual(film.runtime_minutes, 108)
        self.assertEqual(film.imdb_id, "tt42")
        self.assertEqual(film.poster_url, "https://img/x.jpg")

    def test_reuses_existing_by_tmdb_id(self) -> None:
        existing = Film.objects.create(title="Old", tmdb_id="42")
        svc = mock.Mock()
        film = import_film_from_tmdb(42, service=svc)
        self.assertEqual(film.pk, existing.pk)
        svc.get_film_details.assert_not_called()  # no fetch when reusing
        self.assertEqual(Film.objects.filter(tmdb_id="42").count(), 1)

    def test_reuses_existing_by_imdb_id(self) -> None:
        # A film with this imdb_id already exists but under a different (here, no)
        # tmdb_id, so the tmdb_id lookup misses it. Creating anew would violate the
        # imdb_id unique constraint, so we must reuse the existing row instead.
        existing = Film.objects.create(title="Old", imdb_id="tt42")
        svc = mock.Mock()
        svc.get_film_details.return_value = DETAILS
        film = import_film_from_tmdb(42, service=svc)
        self.assertEqual(film.pk, existing.pk)
        self.assertEqual(Film.objects.filter(imdb_id="tt42").count(), 1)  # no duplicate
        film.refresh_from_db()
        self.assertEqual(film.tmdb_id, "42")  # tmdb_id backfilled onto the existing row
