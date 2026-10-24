"""The one place the visitor's IP address is worked out.

Used by the sign-in link throttle, registration and axes lockout alike, so
all of them see the same address.
"""

import ipaddress

from django.conf import settings


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
