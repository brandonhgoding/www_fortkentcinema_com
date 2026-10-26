"""Where Square sends buyers back to, and who they can write to.

Every hosted checkout the site starts (tickets, memberships) needs the
public scheme and host for its redirect URL and the cinema's support
address for Square's receipt page. Both come from settings, not the
request: build_absolute_uri() is wrong behind nginx.
"""

from email.utils import parseaddr
from urllib.parse import urlsplit

from django.conf import settings


def base_url() -> str:
    """Scheme and host for links Square sends the buyer back to; no trailing slash.

    TICKETS_BASE_URL, else the host of SQUARE_WEBHOOK_URL, else "".
    """
    if settings.TICKETS_BASE_URL:
        return settings.TICKETS_BASE_URL.rstrip("/")
    if settings.SQUARE_WEBHOOK_URL:
        parts = urlsplit(settings.SQUARE_WEBHOOK_URL)
        return f"{parts.scheme}://{parts.netloc}"
    return ""


def support_email() -> str:
    """DEFAULT_FROM_EMAIL's address, or "" when unset or on localhost."""
    address = parseaddr(settings.DEFAULT_FROM_EMAIL or "")[1]
    domain = address.rpartition("@")[2].lower()
    if not domain or domain == "localhost":
        return ""
    return address
