"""Rows for the join tests: a tier that sells online and an order for it."""

from audience.models import MembershipTier

from join.models import MembershipOrder

BUYER = {"first_name": "Ann", "last_name": "Lee", "email": "ann@example.com"}


def set_variation(slug: str = "individual",
                  variation_id: str = "VAR-IND") -> MembershipTier:
    """Give a seeded tier its Square variation ID, which makes it sell online."""
    MembershipTier.objects.filter(slug=slug).update(square_variation_id=variation_id)
    return MembershipTier.objects.get(slug=slug)


def make_order(tier_slug: str = "individual", *, status: str = "PENDING",
               **over) -> MembershipOrder:
    tier = MembershipTier.objects.get(slug=tier_slug)
    fields = {**BUYER, "tier": tier, "status": status,
              "total_cents": tier.price * 100}
    if status != "ABANDONED":
        fields["square_order_id"] = "SQ-1"
    fields.update(over)
    return MembershipOrder.objects.create(**fields)
