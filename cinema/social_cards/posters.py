"""Fetching artwork for social cards.

Artwork is never load-bearing: every failure path returns None and the layout
falls back to an empty framed panel.
"""

from __future__ import annotations

import hashlib
import logging
import re
from io import BytesIO

import requests
from django.core.cache import cache
from PIL import Image

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 8
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS_PER_AXIS = 8000
CACHE_TTL_SECONDS = 60 * 60 * 24
CACHE_PREFIX = "social-card-art:"

_TMDB_SIZE_RE = re.compile(
    r"(https?://image\.tmdb\.org/t/p/)(w\d+|h\d+|original)(/)"
)


def upsize_tmdb_url(url: str) -> str:
    """Ask TMDB for the full-resolution file.

    Film.poster_url stores w500 URLs, which upscale badly onto a 1080px canvas.
    Non-TMDB URLs pass through untouched.
    """
    return _TMDB_SIZE_RE.sub(r"\1original\3", url, count=1)


def _download(url: str) -> bytes | None:
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("social card artwork fetch failed: %s", url)
        return None
    content = response.content
    if len(content) > MAX_BYTES:
        logger.warning(
            "social card artwork too large (%d bytes): %s", len(content), url
        )
        return None
    return content


def _decode(data: bytes) -> Image.Image | None:
    try:
        image = Image.open(BytesIO(data))
        width, height = image.size
        if max(width, height) > MAX_PIXELS_PER_AXIS:
            logger.warning("social card artwork too many pixels: %dx%d",
                           width, height)
            return None
        return image.convert("RGB")
    except Exception:
        logger.warning("social card artwork could not be decoded")
        return None


def fetch_artwork(url: str) -> Image.Image | None:
    """Return a decoded RGB image for `url`, or None on any failure."""
    if not url:
        return None
    target = upsize_tmdb_url(url)
    key = CACHE_PREFIX + hashlib.sha256(target.encode()).hexdigest()
    data = cache.get(key)
    if data is None:
        data = _download(target)
        if data is None:
            return None
        cache.set(key, data, CACHE_TTL_SECONDS)
    return _decode(data)
