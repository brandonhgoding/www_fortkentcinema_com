"""Online ticket order lifecycle: start a checkout."""

import datetime

from boxoffice.gateway import GatewayError, SquareGateway, get_gateway
from boxoffice.spec import SQUARE_TIERS
from cinema.models import Showtime
from django.db import transaction

from tickets import availability, pricing
from tickets.models import TicketLine, TicketOrder
from tickets.spec import checkout_spec


class Refused(Exception):
    """The order cannot be placed; .reason is an availability reason string."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def start(
    showtime: Showtime,
    *,
    name: str,
    email: str,
    phone: str,
    quantities: dict[str, int],
    now: datetime.datetime,
    gateway: SquareGateway | None = None,
) -> TicketOrder:
    """Hold the seats as a PENDING order, then ask Square for a payment link.

    Raises Refused before anything is saved. A gateway failure does not raise:
    the order comes back FAILED with the error recorded.
    """
    if gateway is None:
        gateway = get_gateway()
    quantities = {
        tier: quantities.get(tier, 0)
        for tier in SQUARE_TIERS
        if quantities.get(tier, 0) > 0
    }
    wanted = sum(quantities.values())
    with transaction.atomic():
        # Lock the showtime so two buyers cannot both take the last seats.
        showtime = Showtime.objects.select_for_update().get(pk=showtime.pk)
        result = availability.check(showtime, now, square_enabled=gateway is not None)
        if not result.purchasable:
            raise Refused(result.reason)
        if wanted == 0:
            raise Refused("quantity")
        if wanted > result.remaining:
            raise Refused("sold_out")
        variation_ids = availability.variation_ids(showtime.engagement)
        prices = {
            tier: pricing.unit_cents(tier, showtime.starts_at) for tier in quantities
        }
        order = TicketOrder.objects.create(
            showtime=showtime,
            name=name,
            email=email,
            phone=phone,
            total_cents=sum(prices[t] * q for t, q in quantities.items()),
        )
        TicketLine.objects.bulk_create(
            TicketLine(
                order=order,
                tier=tier,
                quantity=quantity,
                unit_cents=prices[tier],
                square_variation_id=variation_ids[tier],
            )
            for tier, quantity in quantities.items()
        )
    # Outside the transaction: never hold the showtime lock across a Square call.
    try:
        link = gateway.create_payment_link(checkout_spec(order, variation_ids))
    except GatewayError as exc:
        order.status = TicketOrder.Status.FAILED
        order.error = str(exc)
        order.save(update_fields=["status", "error"])
        return order
    order.square_order_id = link.order_id
    order.square_checkout_url = link.url
    order.save(update_fields=["square_order_id", "square_checkout_url"])
    return order
