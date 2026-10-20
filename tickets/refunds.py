"""Refund paid online ticket orders through Square, one order or a whole showtime."""

import dataclasses
import logging

from boxoffice.gateway import Gateway, GatewayError, disabled_reason, get_gateway
from boxoffice.pull import mark_refunded
from cinema.models import Showtime
from django.utils import timezone

from tickets.mail import send_refund
from tickets.models import TicketOrder

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class RefundSummary:
    refunded: int
    failed: int


def refund_order(
    order: TicketOrder, *, reason: str, gateway: Gateway | None = None
) -> TicketOrder:
    """Refund a sold order in full and email the buyer.

    Anything not counted as sold (including an order already REFUNDED) comes
    back unchanged with no Square call. A Square failure leaves the status as
    it was with the error stored; a failed email leaves the order REFUNDED
    with the error stored. Never call this inside a transaction.
    """
    if not order.counts_as_sold:
        return order
    gateway = gateway or get_gateway()
    if gateway is None:
        order.error = f"Square sync disabled: {disabled_reason()}"
        order.save(update_fields=["error"])
        return order
    try:
        gateway.refund_payment(
            payment_id=order.square_payment_id,
            amount_cents=order.total_cents,
            idempotency_key=f"refund-{order.number}",
            reason=reason,
        )
    except GatewayError as exc:
        order.error = str(exc)
        order.save(update_fields=["error"])
        return order
    order.status = TicketOrder.Status.REFUNDED
    order.refunded_at = timezone.now()
    order.error = ""
    # The ledger learns now rather than at the next pull of the sale day,
    # which may already be past the pull's lookback.
    mark_refunded(order.square_order_id)
    try:
        send_refund(order)
    except Exception as exc:
        logger.exception("Refund email failed for order %s", order.number)
        order.error = f"Refund email failed: {exc!r}"
    order.save(update_fields=["status", "refunded_at", "error"])
    return order


def refund_showtime(
    showtime: Showtime,
    *,
    reason: str = "Showtime cancelled",
    gateway: Gateway | None = None,
) -> RefundSummary:
    """Refund every sold order on the showtime, oldest first.

    One failed refund does not stop the rest.
    """
    gateway = gateway or get_gateway()
    refunded = failed = 0
    orders = TicketOrder.objects.filter(
        showtime=showtime,
        status__in=[TicketOrder.Status.PAID, TicketOrder.Status.FAILED],
    ).order_by("pk")
    for order in orders:
        if not order.counts_as_sold:
            continue
        order = refund_order(order, reason=reason, gateway=gateway)
        if order.status == TicketOrder.Status.REFUNDED:
            refunded += 1
        else:
            failed += 1
    return RefundSummary(refunded, failed)
