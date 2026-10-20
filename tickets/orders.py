"""Online ticket order lifecycle: start a checkout, confirm, recover, expire."""

import dataclasses
import datetime
import logging

from boxoffice.gateway import Gateway, GatewayError, InvalidPhone, get_gateway
from tickets.tiers import ONLINE_TIERS
from cinema.models import Showtime
from django.db import transaction
from django.utils import timezone
from web.constants import TICKET_HOLD_MINUTES

from tickets import availability, pricing
from tickets.customers import ensure_customer
from tickets.mail import send_ticket
from tickets.models import TicketLine, TicketOrder
from tickets.spec import checkout_spec

logger = logging.getLogger(__name__)


class Refused(Exception):
    """The order cannot be placed; .reason is an availability reason string."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def start(
    showtime: Showtime,
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    quantities: dict[str, int],
    now: datetime.datetime,
    gateway: Gateway | None = None,
) -> TicketOrder:
    """Hold the seats as a PENDING order, then ask Square for a payment link.

    Raises Refused before anything is saved. A gateway failure does not raise:
    the order comes back ABANDONED with the error recorded.
    """
    if gateway is None:
        gateway = get_gateway()
    quantities = {
        tier: quantities.get(tier, 0)
        for tier in ONLINE_TIERS
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
            first_name=first_name,
            last_name=last_name,
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
    order.square_customer_id = ensure_customer(gateway, order)
    order.save(update_fields=["square_customer_id"])
    try:
        link = _create_link(gateway, checkout_spec(order, variation_ids))
    except GatewayError as exc:
        order.status = TicketOrder.Status.ABANDONED
        order.error = str(exc)
        order.save(update_fields=["status", "error"])
        return order
    order.square_order_id = link.order_id
    order.square_checkout_url = link.url
    order.save(update_fields=["square_order_id", "square_checkout_url"])
    return order


def _create_link(gateway: Gateway, spec):
    """Ask Square for the payment link; once more without the phone if it balks.

    Square validates the prefilled phone against the world's numbering plans,
    so a mistyped area code would otherwise cost the buyer their checkout.
    The phone stays on the order for staff. A fresh idempotency key: Square
    refuses a reused key with a different body.
    """
    try:
        return gateway.create_payment_link(spec)
    except InvalidPhone:
        if not spec.buyer_phone:
            raise
        logger.info("Square rejected the phone prefill for %s; retrying without",
                    spec.reference)
        return gateway.create_payment_link(dataclasses.replace(
            spec, buyer_phone="", idempotency_key=f"{spec.idempotency_key}-nophone"))


def confirm_payment(
    order_id: str, payment_id: str, *, paid_at: datetime.datetime | None = None,
    amount_cents: int | None = None,
) -> TicketOrder | None:
    """Mark the order for Square order `order_id` PAID and email the ticket.

    None when no ticket order matches. Already PAID or REFUNDED, or FAILED
    with a payment (the ticket email failed), comes back unchanged, so a
    repeated event sends no second email. An EXPIRED order still pays: the
    buyer was charged. A failed email leaves the order FAILED with the payment
    recorded, which still counts as sold; resend() retries it.

    A payment that does not cover the order's total (defence in depth: Square
    charges the order's total) issues no ticket: the order is left as it was
    with the mismatch on its error, and an error is logged for ADMINS. None
    for amount_cents means the caller could not say, and the check is skipped.
    """
    with transaction.atomic():
        order = (
            TicketOrder.objects.select_for_update()
            .filter(square_order_id=order_id)
            .first()
        )
        if order is None:
            return None
        payable = order.status in (
            TicketOrder.Status.PENDING,
            TicketOrder.Status.EXPIRED,
        ) or (order.status == TicketOrder.Status.FAILED and not order.square_payment_id)
        if not payable:
            return order
        if amount_cents is not None and amount_cents != order.total_cents:
            order.error = (f"Square payment {payment_id} was for {amount_cents} "
                           f"cents but the order total is {order.total_cents}; "
                           "check it before issuing the ticket")
            order.save(update_fields=["error"])
            logger.error("Order %s: %s", order.number, order.error)
            return order
        order.square_payment_id = payment_id
        order.paid_at = paid_at or timezone.now()
        order.status = TicketOrder.Status.PAID
        order.error = ""
        order.save(update_fields=["square_payment_id", "paid_at", "status", "error"])
    # Outside the transaction: the payment is recorded even if the email fails.
    return _send(order)


def handle_square_payment(
    order_id: str, payment_id: str, paid_at: datetime.datetime | None,
    amount_cents: int | None,
) -> bool:
    """The box office webhook's handler: True when the order was one of ours."""
    return confirm_payment(order_id, payment_id, paid_at=paid_at,
                           amount_cents=amount_cents) is not None


def resend(order: TicketOrder) -> TicketOrder:
    """Retry the ticket email for a paid order whose email failed."""
    if order.status != TicketOrder.Status.FAILED or not order.square_payment_id:
        return order
    return _send(order)


def _send(order: TicketOrder) -> TicketOrder:
    try:
        send_ticket(order)
    except Exception as exc:
        logger.exception("Ticket email failed for order %s", order.number)
        status, error = TicketOrder.Status.FAILED, f"Ticket email failed: {exc!r}"
    else:
        status, error = TicketOrder.Status.PAID, ""
    # Conditional: a staff refund made while the email was sending wins.
    TicketOrder.objects.filter(
        pk=order.pk,
        status__in=[
            TicketOrder.Status.PENDING,
            TicketOrder.Status.PAID,
            TicketOrder.Status.FAILED,
        ],
    ).update(status=status, error=error)
    order.refresh_from_db()
    return order


def recover_pending(
    order: TicketOrder, gateway: Gateway | None = None
) -> TicketOrder:
    """Ask Square whether a PENDING order was paid, in case the webhook was lost."""
    _recover(order, gateway)
    return order


def _recover(order: TicketOrder, gateway: Gateway | None) -> bool:
    """recover_pending's work; False when Square could not be asked."""
    if order.status != TicketOrder.Status.PENDING or not order.square_order_id:
        return True
    if gateway is None:
        gateway = get_gateway()
    if gateway is None:
        return False
    try:
        order_data = gateway.retrieve_order(order.square_order_id)
    except GatewayError as exc:
        logger.warning("Could not check order %s with Square: %s", order.number, exc)
        return False
    for tender in order_data.tenders:
        if tender.paid:
            confirmed = confirm_payment(
                order.square_order_id, tender.payment_id,
                paid_at=order_data.paid_at, amount_cents=tender.amount_cents,
            )
            if confirmed is not None:
                order.refresh_from_db()
            break
    return True


def expire_stale(now: datetime.datetime, gateway: Gateway | None = None) -> int:
    """Expire PENDING orders past the hold that Square says are unpaid.

    Orders Square could not be asked about stay PENDING for the next run; past
    the hold they no longer keep seats either way. Returns the count expired.
    """
    cutoff = now - datetime.timedelta(minutes=TICKET_HOLD_MINUTES)
    expired = 0
    stale = TicketOrder.objects.filter(
        status=TicketOrder.Status.PENDING, created_at__lt=cutoff
    )
    for order in stale:
        if not _recover(order, gateway):
            continue
        # Conditional update: a webhook may have paid the order meanwhile.
        expired += TicketOrder.objects.filter(
            pk=order.pk, status=TicketOrder.Status.PENDING
        ).update(status=TicketOrder.Status.EXPIRED)
    return expired
