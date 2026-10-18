"""Turn a TicketOrder into the gateway's CheckoutSpec for a Square payment link."""

from urllib.parse import urlsplit

from boxoffice.gateway import CheckoutLine, CheckoutSpec
from boxoffice.spec import SQUARE_TIERS
from django.conf import settings
from django.urls import reverse

from tickets import pricing
from tickets.models import TicketOrder


def base_url() -> str:
    """Scheme and host for links Square sends the buyer back to; no trailing slash.

    TICKETS_BASE_URL, else the host of SQUARE_WEBHOOK_URL, else "".
    """
    if settings.TICKETS_BASE_URL:
        return settings.TICKETS_BASE_URL.rstrip("/")
    if settings.SQUARE_WEBHOOK_URL:
        parts = urlsplit(settings.SQUARE_WEBHOOK_URL)
        return f"{parts.scheme}://{parts.netloc}"
    return ""


def checkout_spec(order: TicketOrder, variation_ids: dict[str, str]) -> CheckoutSpec:
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
        for tier in SQUARE_TIERS
        if tier in quantities
    )
    return CheckoutSpec(
        reference=order.number,
        showtime_id=order.showtime_id,
        lines=lines,
        redirect_url=base_url() + reverse("tickets:order", args=[order.token]),
        buyer_email=order.email,
        buyer_phone=order.phone,
        # SITE_CONFIG["cinema"] has no email address.
        support_email=settings.DEFAULT_FROM_EMAIL,
        idempotency_key=order.token,
    )
