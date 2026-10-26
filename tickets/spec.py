"""Turn a TicketOrder into the gateway's CheckoutSpec for a Square payment link."""

import re
from boxoffice.gateway import CheckoutLine, CheckoutSpec
from boxoffice.site import base_url, support_email
from tickets.tiers import ONLINE_TIERS
from django.urls import reverse

from tickets import pricing
from tickets.models import TicketOrder


def e164_phone(raw: str) -> str:
    """The typed phone as E.164 for Square's prefill, or "" if it can't be one.

    US numbers gain +1; an already-international number keeps its digits.
    """
    raw = raw.strip()
    plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if plus:
        return "+" + digits if 8 <= len(digits) <= 15 else ""
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return ""


def checkout_spec(order: TicketOrder, variation_ids: dict[str, str]) -> CheckoutSpec:
    """The payment-link request for ``order``; its Square customer rides along."""
    starts_at = order.showtime.starts_at
    quantities = {line.tier: line.quantity for line in order.lines.all()}
    lines = tuple(
        CheckoutLine(
            variation_id=variation_ids[tier],
            name=tier.capitalize(),
            quantity=quantities[tier],
            unit_cents=pricing.unit_cents(tier, starts_at),
            discount_cents=pricing.discount_cents(tier, starts_at) * quantities[tier],
        )
        for tier in ONLINE_TIERS
        if tier in quantities
    )
    return CheckoutSpec(
        reference=order.number,
        showtime_id=order.showtime_id,
        lines=lines,
        redirect_url=base_url() + reverse("tickets:order", args=[order.token]),
        buyer_email=order.email,
        buyer_phone=e164_phone(order.phone),
        # SITE_CONFIG["cinema"] has no email address.
        support_email=support_email(),
        idempotency_key=order.token,
        customer_id=order.square_customer_id,
    )
