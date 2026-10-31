"""The one place the visitor's IP address is worked out.

Used by the registration throttle and axes lockout alike, so
all of them see the same address.
"""

import ipaddress
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# The throttle bucket for a request with no usable address.
UNKNOWN = "unknown"
_warned = False


def request_ip(request):
    """Return the client's IP as a string, or None if it is missing or invalid.

    Behind nginx (USE_PROXY_HEADERS) the address is nginx's X-Real-IP;
    X-Forwarded-For is never read because a visitor can forge it. Otherwise
    it is REMOTE_ADDR.
    """
    meta = getattr(request, "META", None)
    if meta is None:
        return None
    key = "HTTP_X_REAL_IP" if settings.USE_PROXY_HEADERS else "REMOTE_ADDR"
    raw = (meta.get(key) or "").strip()
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        return None
    return raw


def bucket(request) -> str:
    """The key the throttles count this request against: its address, or
    one shared UNKNOWN bucket when there is none.

    No address means a misconfigured proxy (nginx not sending X-Real-IP)
    or a direct bind, never a visitor. Counting those requests together
    makes the mistake show up as lockouts and caps, and the log says why,
    instead of every limit silently switching off.
    """
    global _warned
    ip = request_ip(request)
    if ip is not None:
        return ip
    if not _warned:
        _warned = True
        header = "X-Real-IP" if settings.USE_PROXY_HEADERS else "REMOTE_ADDR"
        logger.warning(
            "No client address on a request (%s missing or invalid); "
            "throttles are counting such requests in one shared bucket.",
            header,
        )
    return UNKNOWN
