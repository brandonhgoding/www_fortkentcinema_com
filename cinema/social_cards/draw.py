"""Drawing primitives for social cards.

Knows about pixels and the Fort Kent Cinema look. Knows nothing about
engagements — everything here takes plain strings, boxes, and colours.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import theme

RGB = tuple[int, int, int]
Box = tuple[int, int, int, int]


def line_height(font: ImageFont.FreeTypeFont, line_spacing: float) -> int:
    """Calculate line height based on font size and line spacing."""
    return int(font.size * line_spacing)


def wrap_lines(
    text: str, font: ImageFont.FreeTypeFont, max_width: float
) -> list[str]:
    """Greedy word wrap. A single word wider than the box is kept whole."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def fit_text(
    text: str,
    font_path: str,
    box_width: int,
    box_height: int,
    max_size: int,
    min_size: int,
    step: int = 4,
    line_spacing: float = 0.98,
) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """Largest size at which `text` wraps into the box.

    If it still does not fit at `min_size` we render at `min_size` anyway and
    allow the overflow — a title that long is a signal to set a shorter
    event_title, not a reason to render something illegible.
    """
    size = max_size
    while size > min_size:
        font = theme.load_font(font_path, size)
        lines = wrap_lines(text, font, box_width)
        widest = max((font.getlength(line) for line in lines), default=0.0)
        height = len(lines) * line_height(font, line_spacing)
        if height <= box_height and widest <= box_width:
            return lines, font
        size -= step
    font = theme.load_font(font_path, min_size)
    return wrap_lines(text, font, box_width), font


def _tint(layer: Image.Image, color: RGB, strength: float) -> Image.Image:
    """Recolour a blurred alpha mask, scaling its opacity."""
    alpha = layer.getchannel("A").point(lambda v: int(v * strength))
    tinted = Image.new("RGBA", layer.size, color + (0,))
    tinted.putalpha(alpha)
    return tinted


def draw_glow_text(
    base: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    origin: tuple[int, int],
    line_spacing: float,
    body_color: RGB,
    accent_color: RGB,
) -> int:
    """Draw glowing text; return the y coordinate just below the last line.

    When the block wraps to two or more lines the final line takes
    `accent_color`, matching the template's cream-headline-with-gold-last-line
    treatment. A single line is drawn entirely in `body_color`.
    """
    x, y = origin
    step = line_height(font, line_spacing)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    for index, line in enumerate(lines):
        is_last = index == len(lines) - 1
        color = accent_color if (len(lines) > 1 and is_last) else body_color
        pen.text((x, y + index * step), line, font=font, fill=color + (255,))

    wide = _tint(
        layer.filter(ImageFilter.GaussianBlur(theme.GLOW_WIDE_RADIUS)),
        theme.GOLD,
        theme.GLOW_WIDE_STRENGTH,
    )
    tight = _tint(
        layer.filter(ImageFilter.GaussianBlur(theme.GLOW_TIGHT_RADIUS)),
        theme.CREAM,
        theme.GLOW_TIGHT_STRENGTH,
    )
    base.alpha_composite(wide)
    base.alpha_composite(tight)
    base.alpha_composite(layer)
    return y + len(lines) * step


def draw_plain_text(
    base: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    origin: tuple[int, int],
    color: RGB,
) -> int:
    """Crisp, unglowed text. Returns the y coordinate below it."""
    pen = ImageDraw.Draw(base)
    pen.text(origin, text, font=font, fill=color + (255,))
    return origin[1] + line_height(font, 1.0)
