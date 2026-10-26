"""The buyer's Square customer profile: found by email or made at checkout."""

import logging

from boxoffice.gateway import Gateway, GatewayError, InvalidPhone

logger = logging.getLogger(__name__)


def ensure_customer(gateway: Gateway, *, first_name: str, last_name: str,
                    email: str, phone: str, key: str, label: str) -> str:
    """The id of the Square customer for this buyer, or "" on failure.

    One profile per email address, never overwritten: a repeat buyer keeps
    whatever Square already holds. ``phone`` is E.164 or ""; one Square
    cannot parse is left off the new profile rather than lose it. ``key``
    seeds the idempotency keys and ``label`` names the order in the log.
    Any Square failure is logged and gives "", because the directory must
    never cost a sale.
    """
    try:
        found = gateway.find_customer(email)
        if found:
            return found
        return _create(gateway, first_name, last_name, email, phone, key)
    except GatewayError as exc:
        logger.warning("Square customer for order %s skipped: %s", label, exc)
        return ""


def _create(gateway: Gateway, first_name: str, last_name: str, email: str,
            phone: str, key: str) -> str:
    fields = {"given_name": first_name, "family_name": last_name,
              "email": email, "idempotency_key": f"customer-{key}"}
    try:
        return gateway.create_customer(phone=phone, **fields)
    except InvalidPhone:
        if not phone:
            raise
        return gateway.create_customer(
            phone="", **{**fields, "idempotency_key": f"customer-{key}-nophone"})
