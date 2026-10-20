from io import StringIO
from unittest import mock

from cinema.models import Film
from django.core.management import call_command
from django.test import TestCase


def details(certification: str) -> dict:
    return {"tmdb_id": 1, "title": "x", "certification": certification}


@mock.patch("cinema.management.commands.backfill_film_ratings.TMDBService")
class BackfillFilmRatingsTests(TestCase):
    def setUp(self) -> None:
        self.unrated = Film.objects.create(title="Hocus Pocus", tmdb_id="9479")
        self.rated = Film.objects.create(title="Dune", tmdb_id="438631", rating="PG-13")
        self.local = Film.objects.create(title="Town Hall Night")  # no TMDB id

    def _run(self, *args) -> str:
        out = StringIO()
        call_command("backfill_film_ratings", *args, stdout=out)
        return out.getvalue()

    def test_fills_only_unrated_films_with_a_tmdb_id(self, service_cls) -> None:
        service_cls.return_value.get_film_details.return_value = details("PG")
        out = self._run()
        self.unrated.refresh_from_db()
        self.rated.refresh_from_db()
        self.assertEqual(self.unrated.rating, "PG")
        self.assertEqual(self.rated.rating, "PG-13")
        service_cls.return_value.get_film_details.assert_called_once_with(9479)
        self.assertIn("Hocus Pocus: PG", out)
        self.assertIn("Rated 1 film", out)

    def test_dry_run_reports_without_saving(self, service_cls) -> None:
        service_cls.return_value.get_film_details.return_value = details("PG")
        out = self._run("--dry-run")
        self.unrated.refresh_from_db()
        self.assertEqual(self.unrated.rating, "")
        self.assertIn("Hocus Pocus: PG", out)
        self.assertIn("Would rate 1 film", out)

    def test_film_without_a_us_certification_is_reported_not_rated(
        self, service_cls
    ) -> None:
        service_cls.return_value.get_film_details.return_value = details("")
        out = self._run()
        self.unrated.refresh_from_db()
        self.assertEqual(self.unrated.rating, "")
        self.assertIn("Hocus Pocus: no US rating on TMDB", out)
        self.assertIn("Rated 0 films", out)

    def test_a_tmdb_failure_is_reported_and_the_rest_continue(
        self, service_cls
    ) -> None:
        from cinema.tmdb import TMDBAPIError

        other = Film.objects.create(title="Jaws", tmdb_id="578")
        service_cls.return_value.get_film_details.side_effect = [
            TMDBAPIError("down"), details("PG")]
        out = self._run()
        other.refresh_from_db()
        self.assertEqual(other.rating, "PG")
        self.assertIn("Hocus Pocus: TMDB error: down", out)
        self.assertIn("Rated 1 film", out)
