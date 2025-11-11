# signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Booking, ScreeningTime
from .services.square_catalog import (
    ensure_square_item_for_booking
    #ensure_square_variation_for_screening,
)


@receiver(post_save, sender=Booking)
def booking_post_save_to_square(sender, instance: Booking, created, **kwargs):
    # On create and on title change we want to ensure Square is current.
    ensure_square_item_for_booking(instance)


# @receiver(post_save, sender=ScreeningTime)
# def screening_post_save_square(sender, instance: ScreeningTime, created, **kwargs):
#     # Only create/update variations for confirmed bookings
#     if instance.booking.confirmed:
#         ensure_square_variation_for_screening(instance)
