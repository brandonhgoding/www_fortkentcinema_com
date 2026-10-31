from boxoffice.models import SquareItem, SquareVariation
from boxoffice.spec import SQUARE_TIERS
from cinema.models import Engagement
from web.constants import TICKET_PRICES


def make_live_item(engagement: Engagement, *, prefix: str = "") -> SquareItem:
    """A pushed Square item for the run, with one variation per tier.

    Square IDs are unique: give each further live item in a test a `prefix`.
    """
    item = SquareItem.objects.create(
        engagement=engagement, square_id=f"{prefix}item-1", name=engagement.title
    )
    for ordinal, tier in enumerate(SQUARE_TIERS):
        SquareVariation.objects.create(
            item=item,
            square_id=f"{prefix}var-{tier}",
            sku=f"fkc-eng-{engagement.pk}-{tier}",
            tier=tier,
            name=tier.title(),
            price_cents=TICKET_PRICES[tier] * 100,
            ordinal=ordinal,
        )
    return item
