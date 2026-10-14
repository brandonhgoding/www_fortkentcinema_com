"""Content rules for social cards.

Turns an Engagement into the exact strings and artwork URLs a card needs.
Deliberately free of Pillow: every rule here is testable without rendering a
pixel.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

from django.utils import timezone
from django.utils.text import slugify

from cinema.models import Engagement, Film

FACEBOOK = "facebook"
INSTAGRAM = "instagram"
# Facebook Page cover photo — a much wider crop than a feed post, with its own
# layout. Artwork selection follows FACEBOOK (its art panel is portrait-ish),
# so only INSTAGRAM needs special-casing in _single_artwork.
FACEBOOK_BANNER = "facebook-banner"
PLATFORMS = (FACEBOOK, INSTAGRAM, FACEBOOK_BANNER)

BADGE_NOW_PLAYING = "NOW PLAYING"
BADGE_COMING_SOON = "COMING SOON"

# Query-param spelling uses underscores; filename spelling uses hyphens.
BADGE_BY_PARAM = {
    "now_playing": BADGE_NOW_PLAYING,
    "coming_soon": BADGE_COMING_SOON,
}
PARAM_BY_BADGE = {badge: param for param, badge in BADGE_BY_PARAM.items()}
BADGE_SLUGS = {
    BADGE_NOW_PLAYING: "now-playing",
    BADGE_COMING_SOON: "coming-soon",
}

WORDMARK = "FORT KENT CINEMA"
FOOTER = "VISIT WWW.FORTKENTCINEMA.COM FOR SHOWTIMES"
FALLBACK_HEADLINE = "FORT KENT CINEMA"

# Vertical crop anchor: 0.0 keeps the top of the source, 0.5 the middle.
CENTRE_CROP = 0.5
TOP_CROP = 0.25


@dataclass(frozen=True)
class Artwork:
    """One image to place on the card, plus how to crop it."""

    url: str
    crop_bias: float


def _month_day(value: datetime.date) -> str:
    # Explicit day formatting rather than %-d, which is not portable.
    return f"{value:%B} {value.day}".upper()


def format_date_line(
    start: datetime.date, end: datetime.date, badge: str
) -> str:
    if start == end:
        return f"ONE NIGHT ONLY · {_month_day(start)}"
    if badge == BADGE_COMING_SOON:
        return f"STARTS {_month_day(start)}"
    return f"NOW THROUGH {_month_day(end)}"


def default_badge(
    engagement: Engagement, today: datetime.date | None = None
) -> str:
    """Coming Soon only for runs that have not started yet."""
    today = today or timezone.localdate()
    if engagement.start_date > today:
        return BADGE_COMING_SOON
    return BADGE_NOW_PLAYING


def _single_artwork(film: Film, platform: str) -> Artwork | None:
    """Best single image for one film on one platform.

    Instagram's artwork band is landscape, so a 16:9 backdrop is a far better
    fit than a 2:3 poster. When only a poster exists we crop toward its top —
    posters put key art up high and title treatments and credits at the bottom.
    """
    if platform == INSTAGRAM:
        if film.backdrop_url:
            return Artwork(film.backdrop_url, CENTRE_CROP)
        if film.poster_url:
            return Artwork(film.poster_url, TOP_CROP)
        return None
    if film.poster_url:
        return Artwork(film.poster_url, CENTRE_CROP)
    return None


def resolve_artwork(
    films: Sequence[Film], platform: str
) -> tuple[Artwork, ...]:
    """Zero, one, or two images.

    Two only when the first two films both have posters — a split panel with
    one half empty looks like a bug, so a partial pair falls back to single.
    """
    if len(films) >= 2:
        posters = [film.poster_url for film in films[:2] if film.poster_url]
        if len(posters) == 2:
            return tuple(Artwork(url, CENTRE_CROP) for url in posters)
    for film in films[:2]:
        art = _single_artwork(film, platform)
        if art is not None:
            return (art,)
    return ()


@dataclass(frozen=True)
class CardData:
    badge: str
    headline: str
    date_line: str
    artwork: tuple[Artwork, ...]
    slug: str
    wordmark: str = WORDMARK
    footer: str = FOOTER

    @classmethod
    def from_engagement(
        cls,
        engagement: Engagement,
        platform: str,
        badge: str | None = None,
        today: datetime.date | None = None,
    ) -> CardData:
        badge = badge or default_badge(engagement, today)
        title = engagement.title.strip()
        return cls(
            badge=badge,
            headline=(title or FALLBACK_HEADLINE).upper(),
            date_line=format_date_line(
                engagement.start_date, engagement.end_date, badge
            ),
            artwork=resolve_artwork(engagement.ordered_films, platform),
            slug=slugify(title) or f"engagement-{engagement.pk}",
        )
