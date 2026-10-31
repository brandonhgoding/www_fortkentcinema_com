"""Confirm a member's email address by an emailed link plus the password.

The link carries a signed token naming the account, its email and a
fingerprint of its password, so registering the address again with a new
password kills older links. Confirming also needs the account's password,
so whoever clicks must be the person who chose it. This module also holds
the registration throttles (per-address and per-IP) and the guess counter
that kills a link after too many wrong passwords.
"""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.utils.crypto import salted_hmac
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from accounts import throttle

logger = logging.getLogger(__name__)

SALT = "accounts.verify-email"
VERIFY_MAX_AGE = 24 * 60 * 60
IP_CAP = 5
IP_WINDOW = 3600


def normalise(email: str) -> str:
    return email.strip().lower()


def _password_fingerprint(user) -> str:
    return salted_hmac(SALT, user.password).hexdigest()[:16]


def make_token(user) -> str:
    return signing.dumps(
        {"u": user.pk, "e": user.email, "p": _password_fingerprint(user)}, salt=SALT
    )


def read_token(token: str):
    """The member a usable token names (verified or not), or None."""
    try:
        data = signing.loads(token, salt=SALT, max_age=VERIFY_MAX_AGE)
        pk, email, fingerprint = data["u"], data["e"], data["p"]
    except (signing.BadSignature, KeyError, TypeError):
        return None
    user = get_user_model().objects.filter(pk=pk).first()
    if (
        user is None
        or user.email != email
        or _password_fingerprint(user) != fingerprint
        or not user.is_active
        or user.is_staff
    ):
        return None
    return user


def ip_allowed(ip: str) -> bool:
    """Count this request against the address's hourly cap (ip is the
    client_ip.bucket() of the request)."""
    return throttle.bump(f"register:ip:{ip}", IP_WINDOW) <= IP_CAP


def claim_address(email: str) -> datetime | None:
    """None if the address was free (now claimed for 300 s); else when it may
    ask again."""
    key = f"register:addr:{email}"
    retry = timezone.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)
    if cache.add(key, retry, settings.PASSWORD_RESET_TIMEOUT):
        return None
    return cache.get(key) or retry


def _failures_key(user) -> str:
    # Keyed on the password too: re-registering sets a new one, which the
    # wrong-password page tells people to do, and leaves nothing of the old
    # one to guess, so its count starts fresh.
    return f"register:verify-fail:{user.pk}:{_password_fingerprint(user)}"


def link_locked(user) -> bool:
    """True once the account's link took AXES_FAILURE_LIMIT wrong passwords
    within AXES_COOLOFF_TIME: the same brake as the sign-in form, so the
    link is not a second place to guess the password."""
    return throttle.count(_failures_key(user)) >= settings.AXES_FAILURE_LIMIT


def record_wrong_password(user) -> None:
    throttle.bump(
        _failures_key(user), int(settings.AXES_COOLOFF_TIME.total_seconds())
    )


def send_verification(request, user) -> None:
    try:
        url = request.build_absolute_uri(
            reverse("verify_email", args=[make_token(user)])
        )
        subject = render_to_string("dashboard/verify_subject.txt").strip()
        body = render_to_string("dashboard/verify_email.txt", {"url": url})
        EmailMessage(subject, body, to=[user.email]).send()
    except Exception:
        logger.exception("Could not send a verification link")


def send_already_registered(request, email: str) -> None:
    try:
        ctx = {
            "login_url": request.build_absolute_uri(reverse("login")),
            "reset_url": request.build_absolute_uri(reverse("password_reset")),
        }
        subject = render_to_string("dashboard/already_registered_subject.txt").strip()
        body = render_to_string("dashboard/already_registered_email.txt", ctx)
        EmailMessage(subject, body, to=[email]).send()
    except Exception:
        logger.exception("Could not send an already-registered notice")
