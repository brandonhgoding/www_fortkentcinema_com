import random
import factory
from faker import Faker

from cinema.models import (
    Ticket,
    TicketRate,
    RateTypes,
    ScreeningTime,
)

fake = Faker()


# --- Helpers so we don't violate uniqueness on rate_type --- #

def get_evening_rate():
    """
    Guarantee an Evening Admission rate exists.
    If it already exists, factory_boy will return it (django_get_or_create).
    """
    rate, _ = TicketRate.objects.get_or_create(
        rate_type=RateTypes.EVENING_ADMISSION,
        defaults={
            "price": "12.00",
            "member_price": "10.00",
        },
    )
    return rate


def get_matinee_rate():
    """
    Guarantee a Matinee Admission rate exists.
    If it already exists, factory_boy will return it (django_get_or_create).
    """
    rate, _ = TicketRate.objects.get_or_create(
        rate_type=RateTypes.MATINEE,
        defaults={
            "price": "8.00",
            "member_price": "7.00",
        },
    )
    return rate


# --- ScreeningTime must be generated elsewhere --- #
# We rely on another factory, e.g. ScreeningTimeFactory,
# and only assign a FK if caller doesn't override.

class TicketFactory(factory.django.DjangoModelFactory):
    """
    Creates a ticket tied to a ScreeningTime.
    Automatically chooses Matinee or Evening based on time.
    Ticket numbers increment like T000001, T000002, etc.
    """

    class Meta:
        model = Ticket

    screening_time = factory.SubFactory(
        "cinema.tests.factories.booking_factories.ScreeningTimeFactory"
    )

    @factory.lazy_attribute
    def rate(self):
        st: ScreeningTime = self.screening_time
        if st.is_matinee:
            return get_matinee_rate()
        return get_evening_rate()

    ticket_number = factory.Sequence(lambda n: f"T{n:06d}")
