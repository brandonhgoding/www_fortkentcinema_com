"""Drawing primitives for social cards.

Knows about pixels and the Fort Kent Cinema look. Knows nothing about
engagements — everything here takes plain strings, boxes, and colours.
"""

from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

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


def _clip_to_box(layer: Image.Image, box: Box) -> Image.Image:
    """Zero out a layer's alpha outside `box`, in place. Returns `layer`."""
    mask = Image.new("L", layer.size, 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    return layer


def draw_glow_text(
    base: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    origin: tuple[int, int],
    line_spacing: float,
    body_color: RGB,
    accent_color: RGB,
    clip_box: Box | None = None,
) -> int:
    """Draw glowing text; return the y coordinate just below the last line.

    When the block wraps to two or more lines the final line takes
    `accent_color`, matching the template's cream-headline-with-gold-last-line
    treatment. A single line is drawn entirely in `body_color`.

    `clip_box`, if given, hard-bounds every pixel drawn (text and glow alike)
    to that rectangle. Callers that size `lines` to fit a box should still
    pass it: `fit_text` deliberately allows overflow at its size floor rather
    than render nothing, and an unbreakable word wider than the box would
    otherwise bleed past it uncontained.
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
    if clip_box is not None:
        wide = _clip_to_box(wide, clip_box)
        tight = _clip_to_box(tight, clip_box)
        layer = _clip_to_box(layer, clip_box)
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


# Fixed peak heights, cycled across the tree line. A literal rather than
# random() so a given card always renders byte-identically.
_TREE_PEAKS = (0.60, 0.95, 0.45, 0.80, 0.35, 0.70, 0.50, 0.90, 0.40, 0.75)
_TREE_SPACING = 30


def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def make_background(size: tuple[int, int]) -> Image.Image:
    """Radial navy field, brighter toward the upper left.

    Rendered tiny and upscaled: a 64x64 gradient resized with LANCZOS is
    smooth, and skips a million per-pixel Python calls.
    """
    small = Image.new("RGB", (64, 64))
    pixels = small.load()
    assert pixels is not None
    centre_x, centre_y = 0.18, 0.30
    for y in range(64):
        for x in range(64):
            dx = (x / 63) - centre_x
            dy = (y / 63) - centre_y
            distance = math.hypot(dx * 1.1, dy * 1.4)
            pixels[x, y] = _lerp(
                theme.INK_CENTRE, theme.INK_EDGE, min(1.0, distance / 0.95)
            )
    return small.resize(size, Image.Resampling.LANCZOS).convert("RGBA")


def draw_trees(base: Image.Image, band_height: int) -> None:
    """Pine silhouette along the bottom edge."""
    width, height = base.size
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    for index, x in enumerate(range(-_TREE_SPACING, width + _TREE_SPACING,
                                    _TREE_SPACING)):
        peak = _TREE_PEAKS[index % len(_TREE_PEAKS)]
        apex_y = height - int(band_height * peak)
        half = _TREE_SPACING
        pen.polygon(
            [(x - half, height), (x, apex_y), (x + half, height)],
            fill=theme.TREE + (215,),
        )
    base.alpha_composite(layer)


def draw_bulbs(
    base: Image.Image,
    start: tuple[int, int],
    end: tuple[int, int],
    count: int,
    radius: int,
) -> None:
    """A marquee bulb strip: evenly spaced glowing gold dots from start to end.

    Works for any straight line, so the same call draws Facebook's vertical
    seam and Instagram's horizontal one.
    """
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    steps = max(count - 1, 1)
    for index in range(count):
        t = index / steps
        cx = round(start[0] + (end[0] - start[0]) * t)
        cy = round(start[1] + (end[1] - start[1]) * t)
        pen.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=theme.GOLD + (255,),
        )
    glow = _tint(
        layer.filter(ImageFilter.GaussianBlur(radius * 2)), theme.GOLD, 0.85
    )
    base.alpha_composite(glow)
    base.alpha_composite(layer)


def cover_crop(
    image: Image.Image, target_width: int, target_height: int, crop_bias: float
) -> Image.Image:
    """Scale to cover the target box, then crop.

    `crop_bias` picks the vertical anchor: 0.0 keeps the top of the source,
    0.5 the middle, 1.0 the bottom. Horizontal crop is always centred.
    """
    source_width, source_height = image.size
    scale = max(target_width / source_width, target_height / source_height)
    scaled = image.resize(
        (max(round(source_width * scale), target_width),
         max(round(source_height * scale), target_height)),
        Image.Resampling.LANCZOS,
    )
    scaled_width, scaled_height = scaled.size
    left = round((scaled_width - target_width) / 2)
    top = round((scaled_height - target_height) * crop_bias)
    return scaled.crop(
        (left, top, left + target_width, top + target_height)
    )


def place_artwork(
    base: Image.Image, image: Image.Image, box: Box, crop_bias: float
) -> None:
    left, top, right, bottom = box
    cropped = cover_crop(image, right - left, bottom - top, crop_bias)
    base.paste(cropped.convert("RGBA"), (left, top))


def fade_edge(
    base: Image.Image, box: Box, direction: str, color: RGB
) -> None:
    """Fade `box` into `color` from one edge.

    "left" fades in from the left edge (Facebook, where artwork meets type);
    "bottom" fades out at the bottom (Instagram, where the band meets the
    solid text area).
    """
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    if direction == "left":
        ramp = Image.linear_gradient("L").rotate(270, expand=True)
        ramp = ramp.resize((width, height), Image.Resampling.BILINEAR)
    elif direction == "bottom":
        ramp = Image.linear_gradient("L").resize(
            (width, height), Image.Resampling.BILINEAR
        )
    else:
        raise ValueError(f"unknown fade direction: {direction}")
    overlay = Image.new("RGBA", (width, height), color + (0,))
    overlay.putalpha(ramp)
    base.alpha_composite(overlay, (left, top))


def draw_dashed_frame(
    base: Image.Image,
    box: Box,
    color: RGB,
    dash: int = 18,
    gap: int = 14,
    width: int = 3,
) -> None:
    """The template's empty-artwork state."""
    left, top, right, bottom = box
    pen = ImageDraw.Draw(base)
    stroke = color + (255,)
    for x in range(left, right, dash + gap):
        end_x = min(x + dash, right)
        pen.line([(x, top), (end_x, top)], fill=stroke, width=width)
        pen.line([(x, bottom), (end_x, bottom)], fill=stroke, width=width)
    for y in range(top, bottom, dash + gap):
        end_y = min(y + dash, bottom)
        pen.line([(left, y), (left, end_y)], fill=stroke, width=width)
        pen.line([(right, y), (right, end_y)], fill=stroke, width=width)


def draw_outlined_badge(
    base: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    origin: tuple[int, int],
    color: RGB,
    padding: tuple[int, int] = (24, 12),
    border: int = 3,
    scrim_color: RGB | None = None,
    scrim_alpha: int = 120,
) -> None:
    """The template's CATEGORY box: text in a thin outlined rectangle.

    `scrim_color`, if given, fills the box with a translucent rectangle
    first — for a badge sitting over bright artwork, where gold-on-gold (or
    gold-on-pale-sky) would otherwise be hard to read.
    """
    x, y = origin
    pad_x, pad_y = padding
    text_width = font.getlength(text)
    text_height = font.size
    box = [x, y, x + round(text_width) + pad_x * 2, y + text_height + pad_y * 2]
    if scrim_color is not None:
        scrim = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(scrim).rectangle(box, fill=scrim_color + (scrim_alpha,))
        base.alpha_composite(scrim)
    pen = ImageDraw.Draw(base)
    pen.rectangle(box, outline=color + (255,), width=border)
    pen.text((x + pad_x, y + pad_y), text, font=font, fill=color + (255,))
