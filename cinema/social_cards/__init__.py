"""Social card rendering for Fort Kent Cinema engagements.

    png, filename = render_card(engagement, FACEBOOK)

Layers: card.py decides *what* goes on the card, posters.py fetches the
artwork, draw.py provides primitives, layouts.py places everything.
"""

from __future__ import annotations

import datetime

from cinema.models import Engagement

from .card import (
    BADGE_BY_PARAM,
    BADGE_COMING_SOON,
    BADGE_NOW_PLAYING,
    BADGE_SLUGS,
    FACEBOOK,
    INSTAGRAM,
    PARAM_BY_BADGE,
    PLATFORMS,
    CardData,
    default_badge,
)
from .layouts import render
from .posters import fetch_artwork

__all__ = [
    "BADGE_BY_PARAM",
    "BADGE_COMING_SOON",
    "BADGE_NOW_PLAYING",
    "BADGE_SLUGS",
    "FACEBOOK",
    "INSTAGRAM",
    "PARAM_BY_BADGE",
    "PLATFORMS",
    "CardData",
    "card_filename",
    "default_badge",
    "fetch_artwork",
    "render_card",
]


def card_filename(card_data: CardData, platform: str) -> str:
    badge_slug = BADGE_SLUGS[card_data.badge]
    return f"fkc-{card_data.slug}-{badge_slug}-{platform}.png"


def render_card(
    engagement: Engagement,
    platform: str,
    badge: str | None = None,
    today: datetime.date | None = None,
) -> tuple[bytes, str]:
    """Render a social card for `engagement`, with its download filename.

    Returns both so callers never rebuild CardData just to name the file.
    Never raises on artwork failure — a card without art still renders.
    """
    data = CardData.from_engagement(engagement, platform, badge, today)
    images = []
    for artwork in data.artwork:
        image = fetch_artwork(artwork.url)
        if image is not None:
            images.append((image, artwork.crop_bias))
    return render(data, platform, images), card_filename(data, platform)
