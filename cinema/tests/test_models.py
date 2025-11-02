from unittest import mock
from unittest.mock import Mock

from django.db import IntegrityError
import datetime
from django.test import TestCase
from django.utils.timezone import now
from cinema.models import Booking, Film, ScreeningTime


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


class ShowtimeListPropertyTests(TestCase):
    def setUp(self):
        # Create a film
        self.film = Film.objects.create(title="Test Film")

        # Create a booking for the film
        self.booking = Booking.objects.create(
            film=self.film,
            booking_start_date=now().date(),
            booking_end_date=now().date() + datetime.timedelta(days=10),
            confirmed=True,
        )

    def test_excludes_past_screening_times(self):
        # Create a past screening time
        past_date = now().date() - datetime.timedelta(days=1)
        ScreeningTime.objects.create(
            booking=self.booking,
            date=past_date,
            time=datetime.time(14, 0),
        )

        self.assertEqual(self.booking.showtime_list, [])

    def test_excludes_screening_times_beyond_6_days(self):
        # Create a screening time beyond 6 days
        future_date = now().date() + datetime.timedelta(days=7)
        ScreeningTime.objects.create(
            booking=self.booking,
            date=future_date,
            time=datetime.time(14, 0),
        )

        self.assertEqual(self.booking.showtime_list, [])

    def test_includes_screening_times_within_6_days(self):
        # Create a screening time within 6 days
        valid_date = now().date() + datetime.timedelta(days=3)
        ScreeningTime.objects.create(
            booking=self.booking,
            date=valid_date,
            time=datetime.time(14, 0),
        )

        showtime_list = self.booking.showtime_list
        self.assertEqual(len(showtime_list), 1)
        self.assertEqual(showtime_list[0]["date"], valid_date)
        self.assertEqual(showtime_list[0]["times"], ["2:00 PM"])

    def test_formats_screening_times_correctly(self):
        # Create multiple screening times on the same day
        valid_date = now().date() + datetime.timedelta(days=2)
        ScreeningTime.objects.create(
            booking=self.booking,
            date=valid_date,
            time=datetime.time(13, 0),
        )
        ScreeningTime.objects.create(
            booking=self.booking,
            date=valid_date,
            time=datetime.time(15, 30),
        )

        showtime_list = self.booking.showtime_list
        self.assertEqual(len(showtime_list), 1)
        self.assertEqual(showtime_list[0]["date"], valid_date)
        self.assertEqual(showtime_list[0]["times"], ["1:00 PM", "3:30 PM"])


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
