"""Fetch a film poster so it can become the Square item's icon."""
import logging

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 10.0


def fetch_poster(url: str) -> bytes | None:
    """The poster's bytes, or None (logged) when it cannot be fetched.

    A poster is decoration on the register tile; nothing else depends on it,
    so every failure here is a warning, never an error.
    """
    if not url:
        return None
    try:
        response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Poster fetch failed for %s: %s", url, exc)
        return None
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        logger.warning("Poster at %s is %s, not an image",
                       url, content_type or "untyped")
        return None
    return response.content
