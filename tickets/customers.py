"""The buyer's Square customer profile: found by email or made at checkout."""

import logging

from boxoffice.gateway import GatewayError, InvalidPhone, SquareGateway

from tickets.models import TicketOrder
from tickets.spec import e164_phone

logger = logging.getLogger(__name__)


def ensure_customer(gateway: SquareGateway, order: TicketOrder) -> str:
    """The id of the Square customer for ``order``'s buyer, or "" on failure.

    One profile per email address, never overwritten: a repeat buyer keeps
    whatever Square already holds. A phone Square cannot parse is left off
    the new profile rather than lose it. Any Square failure is logged and
    gives "", because the directory must never cost a sale.
    """
    try:
        found = gateway.find_customer(order.email)
        if found:
            return found
        return _create(gateway, order, e164_phone(order.phone))
    except GatewayError as exc:
        logger.warning("Square customer for order %s skipped: %s", order.number, exc)
        return ""


def _create(gateway: SquareGateway, order: TicketOrder, phone: str) -> str:
    fields = {"given_name": order.first_name, "family_name": order.last_name,
              "email": order.email, "idempotency_key": f"customer-{order.token}"}
    try:
        return gateway.create_customer(phone=phone, **fields)
    except InvalidPhone:
        if not phone:
            raise
        return gateway.create_customer(
            phone="", **{**fields, "idempotency_key": f"customer-{order.token}-nophone"})
