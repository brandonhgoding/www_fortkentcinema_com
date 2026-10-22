"""Fetch a film poster so it can become the Square item's icon."""
import logging
from io import BytesIO

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

TIMEOUT = 10.0
MAX_BYTES = 5 * 1024 * 1024


def fetch_poster(url: str) -> bytes | None:
    """The poster's bytes, or None (logged) when it cannot be fetched.

    A poster is decoration on the register tile; nothing else depends on it,
    so every failure here is a warning, never an error.

    The URL is Film.poster_url, which TMDB fills but anyone with the Film
    admin can edit, and this runs from the server's network position. So,
    like cinema.social_cards.posters: https only, no redirects (a public
    host could otherwise bounce the fetch to a private one), a size cap,
    and the bytes must decode as an image before they go anywhere.
    """
    if not url:
        return None
    if not url.startswith("https://"):
        logger.warning("Poster url is not https, not fetched: %s", url)
        return None
    try:
        with httpx.stream("GET", url, timeout=TIMEOUT,
                          follow_redirects=False) as response:
            if 300 <= response.status_code < 400:
                logger.warning("Poster url redirected, not followed: %s", url)
                return None
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                logger.warning("Poster at %s is %s, not an image",
                               url, content_type or "untyped")
                return None
            data = BytesIO()
            for chunk in response.iter_bytes():
                if data.tell() + len(chunk) > MAX_BYTES:
                    logger.warning("Poster at %s is over %d bytes, not kept",
                                   url, MAX_BYTES)
                    return None
                data.write(chunk)
    except httpx.HTTPError as exc:
        logger.warning("Poster fetch failed for %s: %s", url, exc)
        return None
    content = data.getvalue()
    try:
        Image.open(BytesIO(content)).verify()
    except Exception:
        logger.warning("Poster at %s does not decode as an image", url)
        return None
    return content
