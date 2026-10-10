"""Turn a paid Square membership order into a member and a term.

Given an order ID, fetch the order from Square, find the line that sells a
membership tier (matched on the tier's ``square_variation_id``), and create or
renew the buyer's membership. Every order with a membership line leaves one
``MembershipSale`` row saying how it went; ``MembershipSale.order_id`` is the
idempotency key, so a repeated event for a sale already entered or skipped
does nothing, and a failed sale is retried.
"""
import dataclasses
import datetime
import logging
from decimal import Decimal

from audience.models import Member, MembershipTerm, MembershipTier
from audience.terms import latest_term, renewal_start
from boxoffice.gateway import (
    GatewayError,
    OrderData,
    OrderLine,
    Recipient,
    SquareGateway,
    disabled_reason,
    get_gateway,
)
from boxoffice.models import MembershipSale
from boxoffice.pull import business_date
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

FINISHED = (MembershipSale.Status.OK, MembershipSale.Status.SKIPPED)


class _Refused(Exception):
    """An order that cannot become a term; its message is the sale's error."""


@dataclasses.dataclass(frozen=True)
class _Buyer:
    display_name: str
    email: str
    phone: str


@dataclasses.dataclass(frozen=True)
class _Facts:
    """What the order says, worked out before the sale row is locked."""
    paid_at: datetime.datetime | None
    tier: MembershipTier
    line_count: int
    quantity: int
    gross_cents: int
    buyer: _Buyer


def split_name(display_name: str) -> tuple[str, str]:
    """First and last name, split on the last space; one word is all first name."""
    parts = display_name.strip().rsplit(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def membership_lines(
    order: OrderData, tiers_by_variation: dict[str, MembershipTier]
) -> list[tuple[OrderLine, MembershipTier]]:
    """Each line that sells a tier, paired with that tier, in order."""
    return [(line, tiers_by_variation[line.catalog_object_id])
            for line in order.lines
            if line.catalog_object_id in tiers_by_variation]


def _tiers_by_variation() -> dict[str, MembershipTier]:
    # Blank means "not sold online"; it must never match a line.
    return {tier.square_variation_id: tier
            for tier in MembershipTier.objects.exclude(square_variation_id="")}


def _buyer(recipient: Recipient | None) -> _Buyer:
    if recipient is None:
        return _Buyer("", "", "")
    # Normalised exactly as Member.save does, so the lookup matches. Square
    # allows longer names and phones than our columns; Postgres would refuse
    # them, so cut them to fit.
    return _Buyer(recipient.display_name[:200],
                  recipient.email_address.strip().lower(),
                  recipient.phone_number[:40])


def _facts(order: OrderData,
           lines: list[tuple[OrderLine, MembershipTier]]) -> _Facts:
    return _Facts(
        paid_at=order.paid_at,
        tier=lines[0][1],
        line_count=len(lines),
        quantity=sum(line.quantity for line, _ in lines),
        gross_cents=sum(line.gross_cents for line, _ in lines),
        buyer=_buyer(order.recipient),
    )


def _finish(sale: MembershipSale, status: str, error: str = "") -> MembershipSale:
    sale.status = status
    sale.error = error
    sale.processed_at = timezone.now()
    sale.save()
    return sale


def _fail_unless_finished(sale_pk: int, error: str) -> MembershipSale:
    """Record a failure that happened before the order was read.

    The row is locked and re-read first: another event for the same order may
    have finished it meanwhile, and overwriting that would get it retried.
    """
    with transaction.atomic():
        sale = MembershipSale.objects.select_for_update().get(pk=sale_pk)
        if sale.status in FINISHED:
            return sale
        return _finish(sale, MembershipSale.Status.FAILED, error)


def order_never_fetched(sale: MembershipSale) -> bool:
    """True when the sale failed before Square's order was read.

    That is the "gateway disabled or gateway error" outcome: both go through
    ``_fail_unless_finished`` before any order data is known, so ``paid_at``
    and ``tier`` are still blank. A placeholder row left by a killed request
    has the same shape. Square's own retry of the event can fix these without
    staff. A fetched order with no payment time also leaves ``paid_at`` blank,
    but its tier is written first; that failure is permanent, so a retry
    would not help and it does not count.
    """
    return (sale.status == MembershipSale.Status.FAILED
            and sale.paid_at is None and sale.tier_id is None)


def _member(buyer: _Buyer) -> Member:
    member = Member.objects.filter(email=buyer.email).first()
    if member is None:
        first_name, last_name = split_name(buyer.display_name)
        return Member.objects.create(first_name=first_name[:100],
                                     last_name=last_name[:100],
                                     email=buyer.email, phone=buyer.phone)
    # Staff own an existing member's name; only fill a phone they lack.
    if not member.phone and buyer.phone:
        member.phone = buyer.phone
        member.save(update_fields=["phone"])
    return member


def _create_term(order_id: str, facts: _Facts) -> MembershipTerm:
    if facts.paid_at is None:
        raise _Refused("Order has no payment time")
    purchase = business_date(facts.paid_at)
    member = _member(facts.buyer)
    latest = latest_term(member.terms.all())
    started_on = purchase if latest is None else renewal_start(latest, purchase)
    if started_on is None:
        raise _Refused("Current term never expires")
    months = facts.tier.duration_months
    try:
        expires_on = MembershipTerm.default_expiry(started_on, months)
    except OverflowError:
        raise _Refused(f"A {months}-month term from {started_on} runs past "
                       "31 December 9999. Enter the term by hand.") from None
    return MembershipTerm.objects.create(
        member=member, tier=facts.tier, started_on=started_on,
        expires_on=expires_on, price_paid=Decimal(facts.gross_cents) / 100,
        purchased_at=purchase, notes=f"Square order {order_id}")


def _attribute(sale_pk: int, order_id: str, facts: _Facts) -> MembershipSale:
    with transaction.atomic():
        sale = MembershipSale.objects.select_for_update().get(pk=sale_pk)
        if sale.status in FINISHED:
            # Another event for this order finished while this one was fetching.
            return sale
        sale.paid_at = facts.paid_at
        sale.tier = facts.tier
        sale.quantity = facts.quantity
        sale.gross_cents = facts.gross_cents
        sale.display_name = facts.buyer.display_name
        sale.email = facts.buyer.email
        sale.phone = facts.buyer.phone
        if facts.quantity != 1 or facts.line_count > 1:
            return _finish(sale, MembershipSale.Status.FAILED,
                           f"Ordered {facts.quantity} memberships; enter by hand")
        if not facts.buyer.email:
            return _finish(sale, MembershipSale.Status.SKIPPED,
                           "No buyer email (register sale)")
        try:
            # A savepoint, so a failure leaves no member or term behind.
            # The OK save is inside it too: if that save fails, the member
            # and term roll back with it and the failure is recorded below.
            with transaction.atomic():
                sale.term = _create_term(order_id, facts)
                return _finish(sale, MembershipSale.Status.OK)
        except _Refused as exc:
            sale.term = None
            return _finish(sale, MembershipSale.Status.FAILED, str(exc))
        except Exception as exc:
            logger.exception("Square membership order %s failed", order_id)
            sale.term = None
            return _finish(sale, MembershipSale.Status.FAILED, repr(exc))


def process_order(order_id: str,
                  gateway: SquareGateway | None = None) -> MembershipSale | None:
    """Record the membership sale in Square order ``order_id``.

    None when the order has no membership line: nothing is recorded.
    """
    # Created FAILED so a request killed mid-way still shows on the dashboard.
    sale, _ = MembershipSale.objects.get_or_create(
        order_id=order_id,
        defaults={"status": MembershipSale.Status.FAILED,
                  "error": "Processing did not finish"})
    if sale.status in FINISHED:
        return sale
    gateway = gateway or get_gateway()
    if gateway is None:
        return _fail_unless_finished(
            sale.pk, f"Square sync disabled: {disabled_reason()}")
    try:
        order = gateway.retrieve_order(order_id)
    except GatewayError as exc:
        return _fail_unless_finished(
            sale.pk, f"Could not fetch the order from Square: {exc}")
    lines = membership_lines(order, _tiers_by_variation())
    if not lines:
        # Not a membership after all: drop the placeholder or earlier failure.
        MembershipSale.objects.filter(
            pk=sale.pk, status=MembershipSale.Status.FAILED).delete()
        return None
    return _attribute(sale.pk, order_id, _facts(order, lines))
