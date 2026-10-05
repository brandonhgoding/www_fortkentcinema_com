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


def priced_tiers() -> list[tuple[str, int]]:
    return [(k, v) for k, v in TICKET_PRICES.items() if isinstance(v, int)]


def desired_item(engagement: Engagement) -> ItemSpec:
    name = (engagement.display_title or "").strip()
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
