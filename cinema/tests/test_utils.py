from cinema.utils import get_currently_playing_films
from cinema.utils import get_upcoming_films
from datetime import datetime, timedelta
from django.test import TestCase
from cinema.models import Film, Booking
from cinema.utils import get_current_or_next_films


class GetCurrentlyPlayingFilmsTests(TestCase):
    def setUp(self):
        # Create test films and bookings
        self.now = datetime.now()
        self.film1 = Film.objects.create(title="Film 1")
        self.film2 = Film.objects.create(title="Film 2")
        self.film3 = Film.objects.create(title="Film 3")

        # Create bookings for the films
        Booking.objects.create(
            film=self.film1,
            booking_start_date=self.now - timedelta(days=1),
            booking_end_date=self.now + timedelta(days=1),
        )
        Booking.objects.create(
            film=self.film2,
            booking_start_date=self.now - timedelta(days=2),
            booking_end_date=self.now + timedelta(days=2),
        )
        Booking.objects.create(
            film=self.film3,
            booking_start_date=self.now + timedelta(days=1),
            booking_end_date=self.now + timedelta(days=3),
        )

    def test_get_currently_playing_films_with_limit(self):
        # Test with a limit of 2
        films = get_currently_playing_films(limit=2, now=self.now)
        self.assertEqual(len(films), 2)
        self.assertIn(self.film1, films)
        self.assertIn(self.film2, films)

    def test_get_currently_playing_films_no_results(self):
        # Test with a time outside any booking range
        future_time = self.now + timedelta(days=10)
        films = get_currently_playing_films(limit=2, now=future_time)
        self.assertEqual(len(films), 0)


class GetUpcomingFilmsTests(TestCase):
    def setUp(self):
        # Create test films and bookings
        self.now = datetime.now()
        self.film1 = Film.objects.create(title="Film 1")
        self.film2 = Film.objects.create(title="Film 2")
        self.film3 = Film.objects.create(title="Film 3")
        self.film4 = Film.objects.create(title="Film 4")

        # Create bookings for the films
        Booking.objects.create(
            film=self.film1,
            booking_start_date=self.now + timedelta(days=1),
            booking_end_date=self.now + timedelta(days=3),
        )
        Booking.objects.create(
            film=self.film2,
            booking_start_date=self.now + timedelta(days=2),
            booking_end_date=self.now + timedelta(days=4),
        )
        Booking.objects.create(
            film=self.film3,
            booking_start_date=self.now + timedelta(days=3),
            booking_end_date=self.now + timedelta(days=5),
        )
        Booking.objects.create(
            film=self.film4,
            booking_start_date=self.now + timedelta(days=4),
            booking_end_date=self.now + timedelta(days=6),
        )

    def test_get_upcoming_films_with_limit(self):
        # Test with a limit of 2
        current_list = [self.film1]
        films = get_upcoming_films(now=self.now, current_list=current_list, needed=2)
        self.assertEqual(len(films), 2)
        self.assertIn(self.film2, films)
        self.assertIn(self.film3, films)
        self.assertNotIn(self.film1, films)

    def test_get_upcoming_films_no_results(self):
        # Test with no upcoming films
        future_time = self.now + timedelta(days=10)
        films = get_upcoming_films(now=future_time, current_list=[], needed=2)
        self.assertEqual(len(films), 0)


class GetCurrentOrNextFilmsTests(TestCase):
    def setUp(self):
        # Create test films and bookings
        self.now = datetime.now()
        self.film1 = Film.objects.create(title="Film 1")
        self.film2 = Film.objects.create(title="Film 2")
        self.film3 = Film.objects.create(title="Film 3")
        self.film4 = Film.objects.create(title="Film 4")

        # Create bookings for the films
        Booking.objects.create(
            film=self.film1,
            booking_start_date=self.now - timedelta(days=1),
            booking_end_date=self.now + timedelta(days=1),
        )
        Booking.objects.create(
            film=self.film2,
            booking_start_date=self.now - timedelta(days=2),
            booking_end_date=self.now + timedelta(days=2),
        )
        Booking.objects.create(
            film=self.film3,
            booking_start_date=self.now + timedelta(days=1),
            booking_end_date=self.now + timedelta(days=3),
        )
        Booking.objects.create(
            film=self.film4,
            booking_start_date=self.now + timedelta(days=2),
            booking_end_date=self.now + timedelta(days=4),
        )

    def test_get_current_or_next_films_with_exact_limit(self):
        # Test when the limit is met with currently playing films
        films = get_current_or_next_films(limit=2, now=self.now)
        self.assertEqual(len(films), 2)
        self.assertIn(self.film1, films)
        self.assertIn(self.film2, films)

    def test_get_current_or_next_films_with_upcoming(self):
        # Test when the limit is not met and includes upcoming films
        films = get_current_or_next_films(limit=3, now=self.now)
        self.assertEqual(len(films), 3)
        self.assertIn(self.film1, films)
        self.assertIn(self.film2, films)
        self.assertIn(self.film3, films)

    def test_get_current_or_next_films_no_results(self):
        # Test when no films are available
        future_time = self.now + timedelta(days=10)
        films = get_current_or_next_films(limit=2, now=future_time)
        self.assertEqual(len(films), 0)
