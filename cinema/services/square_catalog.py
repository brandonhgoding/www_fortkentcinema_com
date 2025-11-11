import enum
import uuid
from django.conf import settings
from cinema.square_client import get_square_client
from cinema.models import Booking, TicketRate

CURRENCY = "USD"  # or from settings


def ensure_square_item_for_booking(booking: Booking) -> str:
    from square import Square
    from square.environment import SquareEnvironment
    import uuid

    if getattr(booking, "_syncing_to_square", False):
        return booking.square_item_id

    booking._syncing_to_square = True

    try:
        client = Square(
            token=settings.SQUARE_ACCESS_TOKEN,
            environment=SquareEnvironment.PRODUCTION,
        )

        idempotency_key = f"booking-{booking.id}-{uuid.uuid4()}"
        variations = []

        for showtime in booking.screening_times.all():
            new_variation = {
                "type": "ITEM_VARIATION",
                "id": f"#default-variation-{showtime.id}",
                "present_at_all_locations": True,
                "item_variation_data": {
                    "name": showtime.screening_time_string,
                    "pricing_type": "FIXED_PRICING",
                    "price_money": {
                        "amount": showtime.ticket_rate,
                        "currency": "USD",
                    },
                },
            }
            variations.append(new_variation)

        response = client.catalog.object.upsert(
            idempotency_key=idempotency_key,
            object={
                "type": "ITEM",
                "id": f"#film-{booking.id}",
                "present_at_all_locations": True,
                "item_data": {
                    "name": booking.film.title,
                    "description": booking.film.description,
                    "variations": variations,
                },
            },
        )

        catalog_object = response.catalog_object

        booking.square_item_id = catalog_object.id
        booking.save(update_fields=["square_item_id"])
    finally:
        booking._syncing_to_square = False

    return booking.square_item_id

