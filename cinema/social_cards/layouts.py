"""Canvas geometry for social cards.

The only module that knows where things sit. Takes already-fetched artwork so
it never touches the network.
"""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

from PIL import Image, ImageFont

from . import draw, theme
from .card import FACEBOOK, FACEBOOK_BANNER, INSTAGRAM, CardData

ArtworkImages = Sequence[tuple[Image.Image, float]]

PANEL_GAP = 8
FOOTER_STRIP_ALPHA = 150
HEADLINE_SPACING = 0.98

# Generous slack around a clipped headline's glow so the halo fades out
# naturally instead of being cut off flat. The one edge that must stay tight
# is whichever edge borders the artwork/bulb column — see the per-platform
# clip boxes below.
HEADLINE_GLOW_MARGIN = 40

# The right edge still needs *some* padding even though it borders artwork
# or bulbs: `fit_text` maximises font size, so the widest line routinely
# lands at 95-99% of the box width, putting the wide gold glow
# (GLOW_WIDE_RADIUS) right on a flush clip edge — a visible vertical seam.
# Facebook's is small because the bulb column sits close by (x=666);
# Instagram's can be as generous as the other edges because nothing sits to
# the headline's right but solid background.
HEADLINE_RIGHT_MARGIN_FACEBOOK = 16
HEADLINE_RIGHT_MARGIN_INSTAGRAM = HEADLINE_GLOW_MARGIN

# Instagram's lower text block (headline + date + wordmark) is bottom-anchored
# above the footer rather than pinned to a fixed top, so it doesn't leave a
# dead gap when the headline wraps to fewer lines than the geometry was tuned
# for. These are the fixed gaps within that block.
INSTAGRAM_HEADLINE_TO_DATE_GAP = 22
INSTAGRAM_DATE_TO_WORDMARK_GAP = 10
INSTAGRAM_TEXT_TO_FOOTER_GAP = 32

# Footer band heights. `draw_footer_strip` centres its text vertically in
# a band that is always full-bleed to the canvas's bottom edge, so the
# band height directly controls how much clear space sits below the text
# ink. Both platforms crop toward centre in feed/story/mobile placements,
# and that crop reaches this footer first — it needs a real safe-area
# margin below it, not just enough room to avoid clipping in the source
# PNG. Tuned for ~28px (Facebook) / ~43px (Instagram) of clearance below
# the text ink, roughly 4-5% of each canvas's height.
FACEBOOK_FOOTER_HEIGHT = 76
INSTAGRAM_FOOTER_HEIGHT = 108

# --- Facebook Page cover geometry -------------------------------------------
# A cover photo is cropped by two things a feed post isn't, and both shape
# this layout:
#
#   1. Mobile shows a narrower slice than desktop, so roughly the outer tenth
#      of each side can disappear. Nothing that must be read goes outside
#      BANNER_SAFE_INSET.
#   2. The Page's profile picture overlaps the bottom-left corner on desktop.
#      BANNER_TEXT_X starts the text column clear of it, and the block is
#      kept well above the bottom edge.
#
# Consequently the cover has NO bottom footer strip — the URL line is the last
# item in the text column instead. A full-bleed bottom band is exactly what
# the profile picture and the Page name sit on top of.
BANNER_SAFE_INSET = 170
BANNER_TEXT_X = 420
BANNER_TEXT_WIDTH = 600
BANNER_ART_LEFT = 1120
BANNER_BULBS_X = 1090
BANNER_BADGE_TOP = 66
BANNER_HEADLINE_TOP = 148
BANNER_HEADLINE_BOX_HEIGHT = 210
BANNER_DATE_GAP = 20
BANNER_WORDMARK_GAP = 10
BANNER_URL_GAP = 16


def _clamp_lines(
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    line_spacing: float,
    box_height: int,
) -> list[str]:
    """Bound how many lines actually get laid out.

    `fit_text` deliberately allows the block to overflow `box_height` once it
    hits `min_size` — a title that long is a signal to shorten it, not a
    reason to render nothing. But layouts.py places fixed elements below the
    headline, so an unbounded line count would push them off the canvas.
    Always keeps at least one line.
    """
    max_lines = max(1, box_height // draw.line_height(font, line_spacing))
    return lines[:max_lines]


def draw_footer_strip(
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

    headline_x = 64
    headline_top = 160
    headline_box_width = 580
    headline_box_height = 220
    lines, headline_font = draw.fit_text(
        data.headline, theme.FONT_BOLD,
        box_width=headline_box_width, box_height=headline_box_height,
        max_size=76, min_size=36,
    )
    lines = _clamp_lines(lines, headline_font, HEADLINE_SPACING, headline_box_height)
    headline_height = len(lines) * draw.line_height(headline_font, HEADLINE_SPACING)
    # Only lightly padded on the right — that edge borders the bulb column
    # and artwork panel at x=672/700, so it can't take the full glow margin.
    # Generous everywhere else so the glow keeps its natural falloff.
    headline_clip_box = (
        headline_x - HEADLINE_GLOW_MARGIN,
        headline_top - HEADLINE_GLOW_MARGIN,
        headline_x + headline_box_width + HEADLINE_RIGHT_MARGIN_FACEBOOK,
        headline_top + headline_height + HEADLINE_GLOW_MARGIN,
    )
    y = draw.draw_glow_text(
        base, lines, headline_font, (headline_x, headline_top), HEADLINE_SPACING,
        theme.CREAM, theme.GOLD, clip_box=headline_clip_box,
    )

    y = draw.draw_plain_text(
        base, data.date_line, theme.load_font(theme.FONT_MEDIUM, 26),
        (64, y + 24), theme.GOLD,
    )
    draw.draw_plain_text(
        base, data.wordmark, theme.load_font(theme.FONT_BOLD, 24),
        (64, y + 12), theme.GOLD,
    )

    draw_footer_strip(
        base, data.footer, height=FACEBOOK_FOOTER_HEIGHT, font_size=18
    )
    return base


def _render_facebook_banner(
    data: CardData, images: ArtworkImages
) -> Image.Image:
    """Facebook Page cover photo.

    Same furniture as the feed card, rearranged for a 2.6:1 crop: the text
    column sits right of the profile-picture zone, and the URL line rides at
    the bottom of that column rather than in a full-bleed footer band.
    """
    width, height = theme.FACEBOOK_BANNER_SIZE
    base = draw.make_background((width, height))

    art_box = (BANNER_ART_LEFT, 0, width, height)
    _draw_artwork_area(base, art_box, images)
    draw.fade_edge(base, art_box, "left", theme.INK)

    draw.draw_trees(base, band_height=86)
    draw.draw_bulbs(
        base, (BANNER_BULBS_X, 22), (BANNER_BULBS_X, height - 22),
        count=9, radius=6,
    )

    draw.draw_outlined_badge(
        base,
        data.badge,
        theme.load_font(theme.FONT_MEDIUM, 24),
        (BANNER_TEXT_X, BANNER_BADGE_TOP),
        theme.GOLD,
    )

    lines, headline_font = draw.fit_text(
        data.headline, theme.FONT_BOLD,
        box_width=BANNER_TEXT_WIDTH, box_height=BANNER_HEADLINE_BOX_HEIGHT,
        max_size=68, min_size=32,
    )
    lines = _clamp_lines(
        lines, headline_font, HEADLINE_SPACING, BANNER_HEADLINE_BOX_HEIGHT
    )
    headline_height = len(lines) * draw.line_height(
        headline_font, HEADLINE_SPACING
    )
    # Right edge lightly padded — it borders the bulb column at
    # BANNER_BULBS_X. Generous elsewhere so the glow keeps its falloff.
    headline_clip_box = (
        BANNER_TEXT_X - HEADLINE_GLOW_MARGIN,
        BANNER_HEADLINE_TOP - HEADLINE_GLOW_MARGIN,
        BANNER_TEXT_X + BANNER_TEXT_WIDTH + HEADLINE_RIGHT_MARGIN_FACEBOOK,
        BANNER_HEADLINE_TOP + headline_height + HEADLINE_GLOW_MARGIN,
    )
    y = draw.draw_glow_text(
        base, lines, headline_font,
        (BANNER_TEXT_X, BANNER_HEADLINE_TOP), HEADLINE_SPACING,
        theme.CREAM, theme.GOLD, clip_box=headline_clip_box,
    )

    y = draw.draw_plain_text(
        base, data.date_line, theme.load_font(theme.FONT_MEDIUM, 26),
        (BANNER_TEXT_X, y + BANNER_DATE_GAP), theme.GOLD,
    )
    y = draw.draw_plain_text(
        base, data.wordmark, theme.load_font(theme.FONT_BOLD, 24),
        (BANNER_TEXT_X, y + BANNER_WORDMARK_GAP), theme.GOLD,
    )
    draw.draw_plain_text(
        base, data.footer, theme.load_font(theme.FONT_MEDIUM, 18),
        (BANNER_TEXT_X, y + BANNER_URL_GAP), theme.CREAM,
    )
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
        scrim_color=theme.INK,
    )

    headline_x = 56
    headline_box_width = 968
    headline_box_height = 190
    lines, headline_font = draw.fit_text(
        data.headline, theme.FONT_BOLD,
        box_width=headline_box_width, box_height=headline_box_height,
        max_size=76, min_size=36,
    )
    lines = _clamp_lines(lines, headline_font, HEADLINE_SPACING, headline_box_height)

    date_font = theme.load_font(theme.FONT_MEDIUM, 28)
    wordmark_font = theme.load_font(theme.FONT_BOLD, 28)
    headline_height = len(lines) * draw.line_height(headline_font, HEADLINE_SPACING)
    date_height = draw.line_height(date_font, 1.0)
    wordmark_height = draw.line_height(wordmark_font, 1.0)
    block_height = (
        headline_height
        + INSTAGRAM_HEADLINE_TO_DATE_GAP
        + date_height
        + INSTAGRAM_DATE_TO_WORDMARK_GAP
        + wordmark_height
    )

    # Bottom-anchored: a fixed gap above the footer regardless of how many
    # lines the headline wrapped to, so a short headline doesn't leave a
    # dead gap and a tall one still clears the bulb seam (block_height is
    # bounded — headline_height can't exceed headline_box_height).
    footer_height = INSTAGRAM_FOOTER_HEIGHT
    footer_top = height - footer_height
    headline_top = footer_top - INSTAGRAM_TEXT_TO_FOOTER_GAP - block_height

    headline_clip_box = (
        headline_x - HEADLINE_GLOW_MARGIN,
        headline_top - HEADLINE_GLOW_MARGIN,
        headline_x + headline_box_width + HEADLINE_RIGHT_MARGIN_INSTAGRAM,
        headline_top + headline_height + HEADLINE_GLOW_MARGIN,
    )
    y = draw.draw_glow_text(
        base, lines, headline_font, (headline_x, headline_top), HEADLINE_SPACING,
        theme.CREAM, theme.GOLD, clip_box=headline_clip_box,
    )

    y = draw.draw_plain_text(
        base, data.date_line, date_font,
        (headline_x, y + INSTAGRAM_HEADLINE_TO_DATE_GAP), theme.GOLD,
    )
    draw.draw_plain_text(
        base, data.wordmark, wordmark_font,
        (headline_x, y + INSTAGRAM_DATE_TO_WORDMARK_GAP), theme.GOLD,
    )

    draw_footer_strip(base, data.footer, height=footer_height, font_size=20)
    return base


def render(
    card_data: CardData, platform: str, images: ArtworkImages
) -> bytes:
    """Render one card to PNG bytes."""
    if platform == FACEBOOK:
        canvas = _render_facebook(card_data, images)
    elif platform == INSTAGRAM:
        canvas = _render_instagram(card_data, images)
    elif platform == FACEBOOK_BANNER:
        canvas = _render_facebook_banner(card_data, images)
    else:
        raise ValueError(f"unknown platform: {platform}")
    buffer = BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
