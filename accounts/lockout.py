from django.conf import settings
from django.core.cache import cache

from accounts.client_ip import request_ip


def lockout_username(request, credentials: dict | None) -> str:
    """The name django-axes counts failed sign-ins against: the email as
    typed, stripped and lowercased, so "A@x.com" and "a@x.com" share one
    count. Matches how User stores and looks up emails."""
    if credentials and credentials.get("username"):
        raw = credentials["username"]
    else:
        raw = request.POST.get("username", "") if request is not None else ""
    return str(raw).strip().lower()


def _ip_key(ip: str) -> str:
    return f"login:ip:{ip}"


def record_failed_login(sender, credentials=None, request=None, **kwargs) -> None:
    """user_login_failed receiver: count the failure against the address for
    AXES_COOLOFF_TIME. Connected in AccountsConfig.ready()."""
    ip = request_ip(request) if request is not None else None
    if ip is None:
        return
    key = _ip_key(ip)
    ttl = int(settings.AXES_COOLOFF_TIME.total_seconds())
    cache.add(key, 0, ttl)
    try:
        cache.incr(key)
    except ValueError:
        cache.add(key, 1, ttl)


def ip_locked(request) -> bool:
    """True once the address failed LOGIN_IP_FAILURE_LIMIT sign-ins, across
    any emails, within the cool-off. The axes lockout is per (email,
    address); this stops one address spraying a password across accounts."""
    ip = request_ip(request)
    if ip is None:
        return False
    return (cache.get(_ip_key(ip)) or 0) >= settings.LOGIN_IP_FAILURE_LIMIT
