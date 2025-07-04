from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

from django.test import TestCase
from django.utils import timezone

from cinema.models import Film  # adjust this import!
from cinema.utils import (ensure_film_omdb_up_to_date,  # adjust this import!
                          update_omdb)


class UpdateOmdbTests(TestCase):
    def setUp(self) -> None:
        self.film = Film.objects.create(imdb_id="tt1234567", omdb_json={})

    @patch("cinema.utils.OpenMovieDatabaseService")
    def test_update_omdb_with_valid_response(self, mock_service_class: Mock) -> None:
        # Arrange
        mock_service = mock_service_class.return_value
        mock_response = MagicMock()
        mock_response.to_json.return_value = {"Title": "Test Movie"}
        mock_service.get_movie_details.return_value = mock_response

        # Act
        update_omdb(self.film)

        # Assert
        mock_service.get_movie_details.assert_called_once_with(imdb_id=self.film.imdb_id)
        self.film.refresh_from_db()
        self.assertEqual(self.film.omdb_json, {"Title": "Test Movie"})

    @patch("cinema.utils.OpenMovieDatabaseService")
    def test_update_omdb_with_no_response(self, mock_service_class: Mock) -> None:
        # Arrange
        mock_service = mock_service_class.return_value
        mock_service.get_movie_details.return_value = None

        # Act
        update_omdb(self.film)

        # Assert
        mock_service.get_movie_details.assert_called_once_with(imdb_id=self.film.imdb_id)
        self.film.refresh_from_db()
        self.assertEqual(self.film.omdb_json, {})  # Should remain unchanged


class EnsureFilmOmdbUpToDateTests(TestCase):
    def setUp(self) -> None:
        self.film = Film.objects.create(imdb_id="tt1234567", omdb_json={})

    @patch("cinema.utils.update_omdb")
    def test_calls_update_when_omdb_json_empty(self, mock_update_omdb: Mock) -> None:
        self.film.omdb_json = {}
        ensure_film_omdb_up_to_date(self.film)
        mock_update_omdb.assert_called_once_with(self.film)

    @patch("cinema.utils.update_omdb")
    def test_calls_update_when_timestamp_older_than_week(self, mock_update_omdb: Mock) -> None:
        old_timestamp = (timezone.now() - timedelta(days=8)).isoformat()
        self.film.omdb_json = {"timestamp": old_timestamp}
        ensure_film_omdb_up_to_date(self.film)
        mock_update_omdb.assert_called_once_with(self.film)

    @patch("cinema.utils.update_omdb")
    def test_does_not_call_update_when_timestamp_newer_than_week(
        self, mock_update_omdb: Mock
    ) -> None:
        recent_timestamp = (timezone.now() - timedelta(days=2)).isoformat()
        self.film.omdb_json = {"timestamp": recent_timestamp}
        ensure_film_omdb_up_to_date(self.film)
        mock_update_omdb.assert_not_called()
