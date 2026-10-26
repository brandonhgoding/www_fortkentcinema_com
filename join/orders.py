"""Membership order lifecycle: start a checkout on Square, recover a lost payment."""

import logging

from audience.models import MembershipTier
from boxoffice.customers import ensure_customer
from boxoffice.gateway import Gateway, GatewayError, get_gateway
from boxoffice.memberships import process_order

from join.models import MembershipOrder
from join.spec import checkout_spec

logger = logging.getLogger(__name__)


class NotSoldOnline(Exception):
    """The tier is unlisted or has no Square variation to sell."""


def start(tier: MembershipTier, *, first_name: str, last_name: str, email: str,
          gateway: Gateway) -> MembershipOrder:
    """Record a PENDING order, then ask Square for its payment link.

    Raises NotSoldOnline before anything is saved. A gateway failure does
    not raise: the order comes back ABANDONED with the error recorded.
    """
    if not tier.show_on_membership_page or not tier.square_variation_id:
        raise NotSoldOnline(tier.slug)
    order = MembershipOrder.objects.create(
        tier=tier, first_name=first_name, last_name=last_name, email=email,
        total_cents=tier.price * 100)
    order.square_customer_id = ensure_customer(
        gateway, first_name=first_name, last_name=last_name, email=order.email,
        phone="", key=order.token, label=order.number)
    order.save(update_fields=["square_customer_id"])
    try:
        link = gateway.create_payment_link(checkout_spec(order))
    except GatewayError as exc:
        order.status = MembershipOrder.Status.ABANDONED
        order.error = str(exc)
        order.save(update_fields=["status", "error"])
        return order
    order.square_order_id = link.order_id
    order.square_checkout_url = link.url
    order.save(update_fields=["square_order_id", "square_checkout_url"])
    return order


def recover_pending(order: MembershipOrder,
                    gateway: Gateway | None = None) -> MembershipOrder:
    """Ask Square whether a PENDING order was paid, in case the webhook was lost.

    A paid order goes through ``process_order`` exactly as the webhook would
    have sent it, so the ledger row, the term and the welcome email all come
    out the same way. Square unreachable: a warning, and the row is left.
    """
    if order.status != MembershipOrder.Status.PENDING or not order.square_order_id:
        return order
    gateway = gateway or get_gateway()
    if gateway is None:
        return order
    try:
        data = gateway.retrieve_order(order.square_order_id)
    except GatewayError as exc:
        logger.warning("Could not check order %s with Square: %s", order.number, exc)
        return order
    if any(tender.paid for tender in data.tenders):
        process_order(order.square_order_id, gateway)
        order.refresh_from_db()
    return order
