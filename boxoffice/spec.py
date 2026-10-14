from dataclasses import dataclass

from cinema.models import Engagement
from web.constants import TICKET_PRICES


@dataclass(frozen=True)
class VariationSpec:
    tier: str
    name: str
    sku: str
    price_cents: int
    ordinal: int


@dataclass(frozen=True)
class ItemSpec:
    engagement_id: int
    name: str
    variations: tuple[VariationSpec, ...]


# The variations on every ticket item, in register order. Matinee and member
# prices are rung as Square discounts, so they stay out of this list.
SQUARE_TIERS = ("adult", "senior", "child")


def priced_tiers() -> list[tuple[str, int]]:
    return [(tier, TICKET_PRICES[tier]) for tier in SQUARE_TIERS]


def desired_item(engagement: Engagement) -> ItemSpec:
    name = (engagement.title or "").strip()
    if not name:
        raise ValueError(
            f"Engagement {engagement.pk} has no title to send to Square")
    if len(name) > 200:  # SquareItem.name max_length
        raise ValueError(
            f"Engagement {engagement.pk} title is longer than 200 characters")
    variations = tuple(
        VariationSpec(
            tier=tier,
            name=tier.title(),
            sku=f"fkc-eng-{engagement.pk}-{tier}",
            price_cents=price * 100,
            ordinal=i,
        )
        for i, (tier, price) in enumerate(priced_tiers())
    )
    return ItemSpec(engagement_id=engagement.pk, name=name, variations=variations)
