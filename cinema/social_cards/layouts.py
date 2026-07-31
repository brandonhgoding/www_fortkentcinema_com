"""Canvas geometry for social cards.

The only module that knows where things sit. Takes already-fetched artwork so
it never touches the network.
"""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

from PIL import Image

from . import draw, theme
from .card import FACEBOOK, INSTAGRAM, CardData

ArtworkImages = Sequence[tuple[Image.Image, float]]

PANEL_GAP = 8
FOOTER_STRIP_ALPHA = 150
HEADLINE_SPACING = 0.98


def _draw_footer_strip(
    base: Image.Image, text: str, height: int, font_size: int
) -> None:
    width, canvas_height = base.size
    top = canvas_height - height
    strip = Image.new(
        "RGBA", (width, height), theme.INK_EDGE + (FOOTER_STRIP_ALPHA,)
    )
    base.alpha_composite(strip, (0, top))
    font = theme.load_font(theme.FONT_MEDIUM, font_size)
    text_width = font.getlength(text)
    draw.draw_plain_text(
        base,
        text,
        font,
        (round((width - text_width) / 2), top + (height - font_size) // 2),
        theme.CREAM,
    )


def _draw_artwork_area(
    base: Image.Image, box: draw.Box, images: ArtworkImages
) -> None:
    """One panel, two panels, or the empty dashed frame."""
    left, top, right, bottom = box
    if len(images) >= 2:
        half = (right - left - PANEL_GAP) // 2
        draw.place_artwork(
            base, images[0][0], (left, top, left + half, bottom), images[0][1]
        )
        draw.place_artwork(
            base,
            images[1][0],
            (right - half, top, right, bottom),
            images[1][1],
        )
        return
    if len(images) == 1:
        draw.place_artwork(base, images[0][0], box, images[0][1])
        return
    draw.draw_dashed_frame(
        base, (left + 24, top + 24, right - 24, bottom - 24), theme.GOLD
    )


def _render_facebook(data: CardData, images: ArtworkImages) -> Image.Image:
    width, height = theme.FACEBOOK_SIZE
    base = draw.make_background((width, height))

    art_box = (700, 0, width, height)
    _draw_artwork_area(base, art_box, images)
    draw.fade_edge(base, art_box, "left", theme.INK)

    draw.draw_trees(base, band_height=110)
    draw.draw_bulbs(base, (672, 24), (672, height - 24), count=11, radius=6)

    draw.draw_outlined_badge(
        base,
        data.badge,
        theme.load_font(theme.FONT_MEDIUM, 24),
        (64, 48),
        theme.GOLD,
    )

    lines, headline_font = draw.fit_text(
        data.headline, theme.FONT_BOLD,
        box_width=580, box_height=220, max_size=76, min_size=36,
    )
    y = draw.draw_glow_text(
        base, lines, headline_font, (64, 160), HEADLINE_SPACING,
        theme.CREAM, theme.GOLD,
    )

    y = draw.draw_plain_text(
        base, data.date_line, theme.load_font(theme.FONT_MEDIUM, 26),
        (64, y + 24), theme.GOLD,
    )
    draw.draw_plain_text(
        base, data.wordmark, theme.load_font(theme.FONT_BOLD, 24),
        (64, y + 12), theme.GOLD,
    )

    _draw_footer_strip(base, data.footer, height=44, font_size=18)
    return base


def _render_instagram(data: CardData, images: ArtworkImages) -> Image.Image:
    width, height = theme.INSTAGRAM_SIZE
    base = draw.make_background((width, height))

    band_bottom = 580
    art_box = (0, 0, width, band_bottom)
    _draw_artwork_area(base, art_box, images)
    draw.fade_edge(base, art_box, "bottom", theme.INK)

    draw.draw_trees(base, band_height=130)
    draw.draw_bulbs(
        base, (40, band_bottom), (width - 40, band_bottom), count=14, radius=7
    )

    draw.draw_outlined_badge(
        base,
        data.badge,
        theme.load_font(theme.FONT_MEDIUM, 28),
        (56, 44),
        theme.GOLD,
    )

    lines, headline_font = draw.fit_text(
        data.headline, theme.FONT_BOLD,
        box_width=968, box_height=190, max_size=76, min_size=36,
    )
    y = draw.draw_glow_text(
        base, lines, headline_font, (56, 630), HEADLINE_SPACING,
        theme.CREAM, theme.GOLD,
    )

    y = draw.draw_plain_text(
        base, data.date_line, theme.load_font(theme.FONT_MEDIUM, 28),
        (56, y + 22), theme.GOLD,
    )
    draw.draw_plain_text(
        base, data.wordmark, theme.load_font(theme.FONT_BOLD, 28),
        (56, y + 10), theme.GOLD,
    )

    _draw_footer_strip(base, data.footer, height=52, font_size=20)
    return base


def render(
    card_data: CardData, platform: str, images: ArtworkImages
) -> bytes:
    """Render one card to PNG bytes."""
    if platform == FACEBOOK:
        canvas = _render_facebook(card_data, images)
    elif platform == INSTAGRAM:
        canvas = _render_instagram(card_data, images)
    else:
        raise ValueError(f"unknown platform: {platform}")
    buffer = BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
