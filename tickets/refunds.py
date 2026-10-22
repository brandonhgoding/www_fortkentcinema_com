"""Refund paid online ticket orders through Square, one order or a whole
showtime, and void orders Square tells us were refunded or charged back
elsewhere."""

import dataclasses
import datetime
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
    return _record_refund(order, timezone.now())


def _record_refund(
    order: TicketOrder, refunded_at: datetime.datetime, note: str = ""
) -> TicketOrder:
    """The money went back: void the ticket, the ledger, and tell the buyer.

    ``note`` is kept on the order (where staff read it) when the refund was
    not the site's own doing, so the row says why.
    """
    order.status = TicketOrder.Status.REFUNDED
    order.refunded_at = refunded_at
    order.error = note
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


def _sold_order(payment_id: str) -> TicketOrder | None:
    if not payment_id:
        return None
    return TicketOrder.objects.filter(square_payment_id=payment_id).first()


def handle_square_refund(
    payment_id: str, refund_id: str, refunded_at: datetime.datetime | None,
    amount_cents: int | None,
) -> bool:
    """The box office webhook's refund handler: True when the payment was ours.

    A refund made from the Square dashboard or POS, in full, voids the
    ticket exactly as the site's Refund button would have. A partial refund
    is staff's call: the order is flagged (the ticket stands until they
    decide) with both amounts on it. An order already REFUNDED is left
    alone, so Square's replays send no second email.
    """
    order = _sold_order(payment_id)
    if order is None:
        return False
    if order.status == TicketOrder.Status.REFUNDED:
        return True
    if amount_cents is not None and amount_cents < order.total_cents:
        order.status = TicketOrder.Status.FAILED
        order.error = (f"Square refund {refund_id} gave back {amount_cents} cents "
                       f"of {order.total_cents}; decide whether the ticket stands")
        order.save(update_fields=["status", "error"])
        return True
    _record_refund(order, refunded_at or timezone.now(),
                   note=f"Refunded in Square ({refund_id}), not on the site")
    return True


# Square's dispute states that mean the money is gone for good.
DISPUTE_LOST = {"LOST", "ACCEPTED"}
DISPUTE_NOTE = "Square dispute"


def handle_square_dispute(
    payment_id: str, dispute_id: str, state: str, reason: str
) -> bool:
    """The box office webhook's dispute handler: True when the payment was ours.

    An open chargeback flags the order for staff but leaves the ticket
    valid, because the cinema may win. A lost (or accepted) one voids it
    like a refund. A won one clears the flag, but only the dispute's own
    flag: an order FAILED for another reason keeps that reason.
    """
    order = _sold_order(payment_id)
    if order is None:
        return False
    if order.status == TicketOrder.Status.REFUNDED:
        return True
    label = f"{DISPUTE_NOTE} {dispute_id} ({reason or 'no reason given'})"
    if state in DISPUTE_LOST:
        _record_refund(order, timezone.now(),
                       note=f"{label} {state.lower()}: the payment was reversed")
        return True
    if state == "WON":
        if order.error.startswith(DISPUTE_NOTE):
            order.status = TicketOrder.Status.PAID
            order.error = ""
            order.save(update_fields=["status", "error"])
        return True
    order.status = TicketOrder.Status.FAILED
    order.error = f"{label} is {state}: the buyer's bank is contesting this payment"
    order.save(update_fields=["status", "error"])
    return True


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
