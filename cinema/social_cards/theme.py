"""Visual constants for Fort Kent Cinema social cards.

Everything about how a card *looks* lives here, so the palette and type scale
can be retuned without touching layout or drawing code. Colours are sampled
from the YouTube thumbnail template (fkc-thumbnail-template-blank.png).
"""

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONTS_DIR = Path(__file__).resolve().parent / "fonts"
FONT_BOLD = str(FONTS_DIR / "Poppins-ExtraBold.ttf")
FONT_MEDIUM = str(FONTS_DIR / "Poppins-SemiBold.ttf")

# Palette
INK = (15, 19, 32)  # base field
INK_CENTRE = (27, 33, 54)  # brighter core of the radial background
INK_EDGE = (11, 14, 23)  # darkest corners
GOLD = (233, 192, 94)
CREAM = (253, 246, 224)
TREE = (5, 7, 12)

FACEBOOK_SIZE = (1200, 630)
INSTAGRAM_SIZE = (1080, 1080)

# Text glow: a tight cream halo over a wide gold bloom.
GLOW_TIGHT_RADIUS = 10
GLOW_WIDE_RADIUS = 34
GLOW_TIGHT_STRENGTH = 0.55
GLOW_WIDE_STRENGTH = 0.35


@lru_cache(maxsize=256)
def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font, memoised.

    Fitting a headline tries many sizes in a loop, so this gets called far more
    often than there are distinct fonts.
    """
    return ImageFont.truetype(path, size)
