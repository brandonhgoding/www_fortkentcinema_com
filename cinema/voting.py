"""Vote casting and its integrity rules.

The protection here is deliberately soft. A determined person can clear
cookies and vote again from a phone, and no CAPTCHA is used because the
friction would cost more real votes than the cheating costs us. The real
defense is the curated ballot: every option is a film we already approved,
so a stuffed ballot still returns something we are happy to screen.

What IS hard: a poll accepts writes only while open and inside its
opens_at/closes_at window, and one browser gets one vote per poll and one
email address gets one vote per poll (database constraints, see
cinema/models/poll.py). There is no per-IP cap: the only address we can
see past the proxy is X-Forwarded-For, which the client writes, so a cap
would stop nobody who meant to get past it.
"""

import uuid

from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import IntegrityError, transaction

from .models import EmailPreference, Vote

VOTER_COOKIE = "fkc_voter"
VOTER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year


class VoteError(Exception):
    """Base for every refusal to record a vote."""


class PollNotOpen(VoteError):
    pass


class AlreadyVoted(VoteError):
    pass


class EmailAlreadyVoted(VoteError):
    pass


class OptionMismatch(VoteError):
    pass


def client_ip(request) -> str | None:
    """Best-effort client address, for audit trails only.

    The leftmost X-Forwarded-For hop is supplied by the client and is
    therefore trivially spoofable — this value must never be used as a
    security control, only recorded as an informational record of who
    said they were connecting. Anything that isn't a well-formed IP
    address (spoofed nonsense included) is discarded rather than
    returned: production's Postgres `inet` columns reject non-IP text
    outright, and a 500 from a public, unauthenticated form is worse
    than a blank audit field.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
    else:
        candidate = request.META.get("REMOTE_ADDR") or ""

    if not candidate:
        return None
    try:
        validate_ipv46_address(candidate)
    except ValidationError:
        return None
    return candidate


def new_voter_key() -> str:
    return str(uuid.uuid4())


def voter_key_from(request) -> str | None:
    return request.COOKIES.get(VOTER_COOKIE) or None


def existing_vote(poll, voter_key: str | None) -> Vote | None:
    if not voter_key:
        return None
    return (
        Vote.objects.filter(poll=poll, voter_key=voter_key)
        .select_related("option", "option__film")
        .first()
    )


def cast_vote(
    poll,
    option,
    voter_key: str,
    email: str = "",
    email_preference: str = EmailPreference.NONE,
) -> Vote:
    """Record one vote, or raise a VoteError subclass explaining the refusal.

    The address is checked here but what to do with it (a mailing-list
    signup) is the caller's business: this module knows nothing about the
    audience app.
    """
    if not poll.is_accepting_votes():
        raise PollNotOpen(f"Poll {poll.pk} is not taking votes.")

    if option.poll_id != poll.pk:
        raise OptionMismatch("That option does not belong to this poll.")

    email = (email or "").strip().lower()

    if Vote.objects.filter(poll=poll, voter_key=voter_key).exists():
        raise AlreadyVoted("This browser has already voted in this poll.")
    if email and Vote.objects.filter(poll=poll, email=email).exists():
        raise EmailAlreadyVoted("This address has already voted in this poll.")

    try:
        with transaction.atomic():
            return Vote.objects.create(
                poll=poll,
                option=option,
                voter_key=voter_key,
                email=email,
                email_preference=email_preference,
            )
    except IntegrityError as exc:
        # Two concurrent requests from the same browser or address. The
        # database constraints are the authority; translate whichever one
        # fired into our own error.
        if Vote.objects.filter(poll=poll, voter_key=voter_key).exists():
            raise AlreadyVoted("This browser has already voted in this poll.") from exc
        raise EmailAlreadyVoted("This address has already voted in this poll.") from exc
