"""Turn a MembershipOrder into the gateway's CheckoutSpec for a Square payment link."""

from boxoffice.gateway import CheckoutLine, CheckoutSpec
from boxoffice.site import base_url, support_email
from django.urls import reverse

from join.models import MembershipOrder


def checkout_spec(order: MembershipOrder) -> CheckoutSpec:
    """One line at the tier's price, explicit so a catalog lag cannot change it."""
    tier = order.tier
    line = CheckoutLine(
        variation_id=tier.square_variation_id,
        name=tier.name,
        quantity=1,
        unit_cents=order.total_cents,
        discount_cents=0,
    )
    return CheckoutSpec(
        reference=order.number,
        lines=(line,),
        redirect_url=base_url() + reverse("join:order", args=[order.token]),
        buyer_email=order.email,
        buyer_phone="",
        support_email=support_email(),
        idempotency_key=order.token,
        customer_id=order.square_customer_id,
    )
