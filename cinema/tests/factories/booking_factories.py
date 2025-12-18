# tests/factories/booking_factories.py

import random
from datetime import timedelta, time as dt_time

import factory
from faker import Faker
from django.utils import timezone

from cinema.models import Booking, ScreeningTime  # <-- adjust "cinema" to your app label

fake = Faker()


class BookingFactory(factory.django.DjangoModelFactory):
    """
    Creates a Booking with a film and a realistic date range.
    - booking_start_date: ~2 days before/after today
    - booking_end_date: 5–10 days after start
    """

    class Meta:
        model = Booking

    film = factory.SubFactory("cinema.tests.factories.film_factories.FilmFactory")

    @factory.lazy_attribute
    def booking_start_date(self):
        # anywhere from 2 days ago to 2 days ahead
        return timezone.localdate() + timedelta(days=random.randint(-2, 2))

    @factory.lazy_attribute
    def booking_end_date(self):
        # 5–10 days after start
        return self.booking_start_date + timedelta(days=random.randint(5, 10))

    confirmed = True

    # percentage terms: e.g. 45.00–65.00
    terms_percentage = factory.Faker(
        "pydecimal",
        left_digits=2,
        right_digits=2,
        positive=True,
        min_value=45,
        max_value=65,
    )

    # guarantee: 500–2000
    terms_guarantee = factory.Faker(
        "pydecimal",
        left_digits=4,
        right_digits=2,
        positive=True,
        min_value=500,
        max_value=2000,
    )

    auditorium = Booking.AuditoriumChoices.SOUTH_AUDITORIUM
    square_id = None
    square_version = None


class ScreeningTimeFactory(factory.django.DjangoModelFactory):
    """
    ScreeningTime for a given booking.
    - date: random date within the booking date range
    - time: ~30% matinee (1–3pm), ~70% evening (6–9pm)
    """

    class Meta:
        model = ScreeningTime

    booking = factory.SubFactory(BookingFactory)

    @factory.lazy_attribute
    def date(self):
        start = self.booking.booking_start_date
        end = self.booking.booking_end_date
        delta_days = (end - start).days
        if delta_days < 0:
            # fallback: just use start date if something weird happens
            return start
        offset = random.randint(0, delta_days)
        return start + timedelta(days=offset)

    @factory.lazy_attribute
    def time(self):
        # choose matinee or evening window
        if random.random() < 0.3:  # ~30% matinees
            hour = random.randint(13, 15)  # 1–3pm
        else:
            hour = random.randint(18, 21)  # 6–9pm
        minute = random.choice([0, 15, 30, 45])
        return dt_time(hour=hour, minute=minute, second=0, microsecond=0)

    square_variation_id = None
    square_variation_version = None
    open_captions = factory.Faker("boolean", chance_of_getting_true=10)
