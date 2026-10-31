from django.conf import settings

from accounts import throttle
from accounts.client_ip import bucket


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
    if request is None:
        # Not a login form: the test client or a shell, nothing to count.
        return
    throttle.bump(
        _ip_key(bucket(request)), int(settings.AXES_COOLOFF_TIME.total_seconds())
    )


def ip_locked(request) -> bool:
    """True once the address failed LOGIN_IP_FAILURE_LIMIT sign-ins, across
    any emails, within the cool-off. The axes lockout is per (email,
    address); this stops one address spraying a password across accounts."""
    return (
        throttle.count(_ip_key(bucket(request))) >= settings.LOGIN_IP_FAILURE_LIMIT
    )
