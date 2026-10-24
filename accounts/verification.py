"""Confirm a member's email address by an emailed single-use link.

The link carries a signed token naming the account and its email. It is
spent once the account's email_verified_at is set. This module also holds
the registration throttles (per-address and per-IP).
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

SALT = "accounts.verify-email"
VERIFY_MAX_AGE = 24 * 60 * 60
IP_CAP = 5
IP_WINDOW = 3600


def normalise(email: str) -> str:
    return email.strip().lower()


def make_token(user) -> str:
    return signing.dumps({"u": user.pk, "e": user.email}, salt=SALT)


def read_token(token: str):
    """The unverified member a usable token names, or None."""
    try:
        data = signing.loads(token, salt=SALT, max_age=VERIFY_MAX_AGE)
        pk, email = data["u"], data["e"]
    except (signing.BadSignature, KeyError, TypeError):
        return None
    user = get_user_model().objects.filter(pk=pk).first()
    if (
        user is None
        or user.email != email
        or not user.is_active
        or user.is_staff
        or user.email_verified_at is not None
    ):
        return None
    return user


def ip_allowed(ip: str | None) -> bool:
    """Count this request against the IP's hourly cap."""
    if ip is None:
        return True
    key = f"register:ip:{ip}"
    cache.add(key, 0, IP_WINDOW)
    try:
        count = cache.incr(key)
    except ValueError:
        # The key expired between add and incr: start a fresh window.
        cache.add(key, 1, IP_WINDOW)
        count = 1
    return count <= IP_CAP


def claim_address(email: str) -> datetime | None:
    """None if the address was free (now claimed for 300 s); else when it may
    ask again."""
    key = f"register:addr:{email}"
    retry = timezone.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)
    if cache.add(key, retry, settings.PASSWORD_RESET_TIMEOUT):
        return None
    return cache.get(key) or retry


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
