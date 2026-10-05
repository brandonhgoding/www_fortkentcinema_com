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
from django.core.cache import caches
from PIL import Image

logger = logging.getLogger(__name__)

# Own alias (see fortkentcinema/settings.py CACHES) rather than the default
# cache: entries here are raw artwork bytes up to MAX_BYTES each, which
# would otherwise share the default alias's eviction budget with the rest
# of the app.
cache = caches["social_cards"]

TIMEOUT_SECONDS = 8
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS_PER_AXIS = 8000
CACHE_TTL_SECONDS = 60 * 60 * 24
CACHE_PREFIX = "social-card-art:"

_TMDB_SIZE_RE = re.compile(
    r"^(https?://image\.tmdb\.org/t/p/)(w\d+|h\d+|original)(/)"
)


def upsize_tmdb_url(url: str) -> str:
    """Ask TMDB for the full-resolution file.

    Film.poster_url stores w500 URLs, which upscale badly onto a 1080px canvas.
    Non-TMDB URLs pass through untouched.
    """
    return _TMDB_SIZE_RE.sub(r"\1original\3", url, count=1)


def _download(url: str) -> bytes | None:
    if not url.startswith("https://"):
        logger.warning("social card artwork url is not https: %s", url)
        return None
    try:
        with requests.get(
            url, timeout=TIMEOUT_SECONDS, stream=True, allow_redirects=False
        ) as response:
            if 300 <= response.status_code < 400:
                logger.warning(
                    "social card artwork url redirected: %s", url
                )
                return None
            response.raise_for_status()
            data = BytesIO()
            total_size = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive new chunks
                    total_size += len(chunk)
                    if total_size > MAX_BYTES:
                        logger.warning(
                            "social card artwork too large (%d bytes): %s",
                            total_size, url
                        )
                        return None
                    data.write(chunk)
            return data.getvalue()
    except requests.RequestException:
        logger.warning("social card artwork fetch failed: %s", url)
        return None


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


def _fetch(url: str) -> Image.Image | None:
    key = CACHE_PREFIX + hashlib.sha256(url.encode()).hexdigest()
    data = cache.get(key)
    if data is not None:
        return _decode(data)
    data = _download(url)
    if data is None:
        return None
    image = _decode(data)
    # Only cache what decodes, so a bad response is retried next time
    # instead of blanking the artwork for a day.
    if image is not None:
        cache.set(key, data, CACHE_TTL_SECONDS)
    return image


def fetch_artwork(url: str) -> Image.Image | None:
    """Return a decoded RGB image for `url`, or None on any failure.

    Tries TMDB's full-resolution file first, then the stored URL as given,
    so an original too big for MAX_BYTES or MAX_PIXELS_PER_AXIS still
    gets the w500 rather than an empty frame.
    """
    if not url:
        return None
    for candidate in dict.fromkeys([upsize_tmdb_url(url), url]):
        image = _fetch(candidate)
        if image is not None:
            return image
    return None
