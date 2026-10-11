"""Header image optimisation.

Header images went up as whatever the author had: 2-3 MB PNGs from an image
generator or a phone, 1200-1700px wide, shown in ~350px cards. /blog/ weighed
10.5 MB. An upload that is wider than MAX_WIDTH or heavier than
RECOMPRESS_OVER_BYTES is now resized and saved as WebP; anything already
small is stored exactly as uploaded.

Called from BlogPost.save() for new uploads, and by the optimise_blog_images
command for images that went up before this existed.
"""

import io
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

# The post page shows the header full-bleed; 1600px covers a desktop hero
# without shipping a 4K original to a phone.
MAX_WIDTH = 1600
RECOMPRESS_OVER_BYTES = 300_000
WEBP_QUALITY = 80


def optimise_header_image(file) -> ContentFile | None:
    """A smaller WebP copy of `file`, or None if it should be stored as is.

    None for images already within budget, for animations (WebP would keep
    only the first frame here), for anything Pillow can't read — validating
    the upload is ImageField's job, not this one's — and when re-encoding
    would not actually save anything.
    """
    file.seek(0)
    original = file.read()
    file.seek(0)
    try:
        img = Image.open(io.BytesIO(original))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return None

    if getattr(img, "is_animated", False):
        return None
    if img.width <= MAX_WIDTH and len(original) <= RECOMPRESS_OVER_BYTES:
        return None

    # Phone photos carry their rotation in EXIF, which WebP output drops.
    img = ImageOps.exif_transpose(img)
    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    img = img.convert("RGBA" if has_alpha else "RGB")
    if img.width > MAX_WIDTH:
        height = round(img.height * MAX_WIDTH / img.width)
        img = img.resize((MAX_WIDTH, height), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=WEBP_QUALITY, method=6)
    if buf.tell() >= len(original):
        return None
    return ContentFile(buf.getvalue(), name=f"{Path(file.name).stem}.webp")
