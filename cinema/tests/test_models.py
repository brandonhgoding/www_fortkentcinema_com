from unittest import mock
from unittest.mock import Mock

from django.db import IntegrityError
from django.test import TestCase

from cinema.models import Film, ScreeningTime


class FilmModelTest(TestCase):
    def setUp(self) -> None:
        self.film = Film.objects.create(title="A Good Film", imdb_id="1234", youtube_id="5678")

    def test_imdb_id_is_unique(self) -> None:
        with self.assertRaises(IntegrityError):
            Film.objects.create(title="An OK Film", imdb_id="1234", youtube_id="9875")

    def test_youtube_id_is_unique(self) -> None:
        with self.assertRaises(IntegrityError):
            Film.objects.create(title="An OK Film", youtube_id="5678", imdb_id="9876")

    @mock.patch("core.mixins.slugify")
    def test_slugify_is_called_if_slug_is_none(self, mock_slugify: Mock) -> None:
        mock_slugify.return_value = "boom-slug"
        self.film.slug = None
        self.film.save()
        mock_slugify.assert_called_once_with("A Good Film")


class BookingModelTest(TestCase):
    def setUp(self) -> None:
        self.film = Film.objects.create(title="A Good Film", imdb_id="1234", youtube_id="5678")
        self.booking = self.film.bookings.create(
            booking_start_date="2023-01-01",
            booking_end_date="2023-01-10",
            confirmed=True,
        )

    def test_booking_str(self) -> None:
        expected_str = (
            f"Booking for {self.film.title} from {self.booking.booking_start_date} "
            f"to {self.booking.booking_end_date}"
        )
        self.assertEqual(str(self.booking), expected_str)

    def test_is_active(self) -> None:
        with mock.patch("django.utils.timezone.now") as mock_now:
            mock_now.return_value = mock.Mock(date=lambda: "2023-01-05")
            self.assertTrue(self.booking.is_active)

    def test_is_not_active(self) -> None:
        with mock.patch("django.utils.timezone.now") as mock_now:
            # Case 1: Before booking start date
            mock_now.return_value = mock.Mock(date=lambda: "2022-12-31")
            self.assertFalse(self.booking.is_active)
            # Case 2: After booking end date
            mock_now.return_value = mock.Mock(date=lambda: "2023-01-11")
            self.assertFalse(self.booking.is_active)

    def test_is_confirmed(self) -> None:
        self.assertTrue(self.booking.is_confirmed)

    def test_is_not_confirmed(self) -> None:
        self.booking.confirmed = False
        self.assertFalse(self.booking.is_confirmed)


class PlayDateModelTest(TestCase):
    def setUp(self) -> None:
        self.film = Film.objects.create(title="A Good Film", imdb_id="1234", youtube_id="5678")
        self.booking = self.film.bookings.create(
            booking_start_date="2023-01-01",
            booking_end_date="2023-01-10",
            confirmed=True,
        )
        self.play_date = self.booking.screening_times.create(date="2023-01-01", time="15:00:00")

    def test_play_date_str(self) -> None:
        expected_str = f"{self.film.title} on {self.play_date.date} at {self.play_date.time}"
        self.assertEqual(str(self.play_date), expected_str)

    def test_is_matinee(self) -> None:
        self.assertTrue(self.play_date.is_matinee)

    def test_is_not_matinee(self) -> None:
        self.play_date.time = "17:00:00"
        self.assertFalse(self.play_date.is_matinee)

    def test_unique_together(self) -> None:
        with self.assertRaises(IntegrityError):
            ScreeningTime.objects.create(booking=self.booking, date="2023-01-01", time="15:00:00")
