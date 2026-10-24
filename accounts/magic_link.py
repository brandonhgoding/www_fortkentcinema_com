"""Sign in (and register) by an emailed one-time link.

The link carries a signed token naming the address and the account's
last_login when it was issued. Signing in moves last_login, so a link works
once, and for a brand-new address creating the account does the same.
"""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

SALT = "accounts.magic-link"
IP_CAP = 5
IP_WINDOW = 3600


def normalise(email: str) -> str:
    return email.strip().lower()


def _find_user(email: str):
    return get_user_model().objects.filter(email__iexact=email).first()


def _stamp(user) -> str:
    return user.last_login.isoformat() if user and user.last_login else ""


def link_allowed_for(user) -> bool:
    """No account yet, or an active member; never staff or a closed account."""
    return user is None or (user.is_active and not user.is_staff)


def make_token(email: str) -> str:
    return signing.dumps({"e": email, "l": _stamp(_find_user(email))}, salt=SALT)


def read_token(token: str) -> str | None:
    """The address a usable token names, or None."""
    try:
        data = signing.loads(
            token, salt=SALT, max_age=settings.PASSWORD_RESET_TIMEOUT
        )
        email, stamp = data["e"], data["l"]
    except (signing.BadSignature, KeyError, TypeError):
        return None
    user = _find_user(email)
    if stamp != _stamp(user) or not link_allowed_for(user):
        return None
    return email


def ip_allowed(ip: str | None) -> bool:
    """Count this request against the IP's hourly cap."""
    if ip is None:
        return True
    key = f"magic-link:ip:{ip}"
    cache.add(key, 0, IP_WINDOW)
    return cache.incr(key) <= IP_CAP


def claim_address(email: str) -> datetime | None:
    """None if the address was free (now claimed for 300 s); else when it may
    ask again."""
    key = f"magic-link:addr:{email}"
    retry = timezone.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)
    if cache.add(key, retry, settings.PASSWORD_RESET_TIMEOUT):
        return None
    return cache.get(key) or retry


def send_link(request, email: str) -> None:
    try:
        url = request.build_absolute_uri(
            reverse("magic_link_sign_in", args=[make_token(email)])
        )
        subject = render_to_string("dashboard/magic_link_subject.txt").strip()
        body = render_to_string("dashboard/magic_link_email.txt", {"url": url})
        EmailMessage(subject, body, to=[email]).send()
    except Exception:
        logger.exception("Could not send a sign-in link")
