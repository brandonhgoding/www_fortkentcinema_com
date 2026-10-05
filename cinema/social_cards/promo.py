"""Standing promo cards: one fixed image per marketing page.

Unlike card.py, nothing here comes from the database. These are the Open
Graph images for pages that are always about the same thing — /sponsor/ is
not a film, so there is no Engagement to describe and no poster to place.

They reuse draw.py and theme.py so a promo card and a showtime card are
recognisably the same house style: the radial navy field, the gold marquee
bulbs, the pine band, the glowing cream headline.

Rendering is deterministic — same code, same bytes — so the committed file
can always be regenerated from source rather than being an orphan binary:

    python manage.py render_promo_cards
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from . import draw, theme
from .layouts import draw_footer_strip

SPONSOR_BADGE = "FOR LOCAL BUSINESS"
SPONSOR_HEADLINE = "PUT YOUR BUSINESS ON THE BIG SCREEN"
SPONSOR_SUBLINE = "SPONSOR A FILM · FROM $299"
SPONSOR_WORDMARK = "FORT KENT CINEMA"
SPONSOR_FOOTER = "WWW.FORTKENTCINEMA.COM/SPONSOR"

# The bulb columns that frame the text, and the gutter the text lives in.
# Symmetric, unlike the feed card's single seam at x=672 — that one divides
# text from artwork, and there is no artwork here to divide from.
BULB_INSET = 52
TEXT_MARGIN = 130

FOOTER_HEIGHT = 76
TREE_BAND = 158

HEADLINE_SPACING = 0.98
GLOW_MARGIN = 40


def _centre_x(width: float, canvas_width: int) -> int:
    return round((canvas_width - width) / 2)


def _draw_centred_glow(
    base: Image.Image,
    lines: list[str],
    font,
    top: int,
    body_color: tuple[int, int, int],
) -> int:
    """Centre each line on its own.

    draw_glow_text puts every line at one x, which is right for the
    left-aligned feed card and wrong here. Drawing line by line also means
    the two-line "last line goes gold" rule never fires — this card gets its
    accent from the gold subline underneath instead.
    """
    width, _ = base.size
    step = draw.line_height(font, HEADLINE_SPACING)
    y = top
    for line in lines:
        x = _centre_x(font.getlength(line), width)
        clip = (
            x - GLOW_MARGIN,
            y - GLOW_MARGIN,
            x + round(font.getlength(line)) + GLOW_MARGIN,
            y + step + GLOW_MARGIN,
        )
        draw.draw_glow_text(
            base, [line], font, (x, y), HEADLINE_SPACING,
            body_color, theme.GOLD, clip_box=clip,
        )
        y += step
    return y


def _draw_centred_plain(
    base: Image.Image, text: str, font, top: int, color
) -> int:
    width, _ = base.size
    return draw.draw_plain_text(
        base, text, font, (_centre_x(font.getlength(text), width), top), color
    )


def render_sponsor_card() -> Image.Image:
    """The Open Graph card for /sponsor/, at Facebook's 1200x630."""
    width, height = theme.FACEBOOK_SIZE
    base = draw.make_background((width, height))

    draw.draw_trees(base, band_height=TREE_BAND)

    # Two bulb columns framing the text, stopping above the footer strip so
    # the bottom bulb never sits half-buried in the band.
    bulb_bottom = height - FOOTER_HEIGHT - 24
    for x in (BULB_INSET, width - BULB_INSET):
        draw.draw_bulbs(base, (x, 40), (x, bulb_bottom), count=10, radius=6)

    badge_font = theme.load_font(theme.FONT_MEDIUM, 24)
    badge_width = badge_font.getlength(SPONSOR_BADGE) + 48
    draw.draw_outlined_badge(
        base,
        SPONSOR_BADGE,
        badge_font,
        (_centre_x(badge_width, width), 66),
        theme.GOLD,
    )

    lines, headline_font = draw.fit_text(
        SPONSOR_HEADLINE,
        theme.FONT_BOLD,
        box_width=width - TEXT_MARGIN * 2,
        box_height=230,
        max_size=86,
        min_size=40,
    )
    y = _draw_centred_glow(base, lines, headline_font, 196, theme.CREAM)

    y = _draw_centred_plain(
        base, SPONSOR_SUBLINE, theme.load_font(theme.FONT_MEDIUM, 30),
        y + 30, theme.GOLD,
    )
    _draw_centred_plain(
        base, SPONSOR_WORDMARK, theme.load_font(theme.FONT_BOLD, 24),
        y + 20, theme.GOLD,
    )

    draw_footer_strip(base, SPONSOR_FOOTER, height=FOOTER_HEIGHT, font_size=18)
    return base


def to_jpeg(image: Image.Image, quality: int = 88) -> bytes:
    """JPEG bytes with no metadata.

    JPEG rather than the PNG the feed cards use, to match og-image.jpg and
    og-history.jpg — and because a flat gradient card at this size is a
    third the bytes as JPEG. Pillow writes no EXIF unless asked, so the
    output carries none.
    """
    buffer = BytesIO()
    image.convert("RGB").save(
        buffer, format="JPEG", quality=quality, optimize=True, progressive=True
    )
    return buffer.getvalue()
