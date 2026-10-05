"""Vote casting and its integrity rules.

The protection here is deliberately soft. A determined person with a few
email addresses can vote a few times, and no CAPTCHA is used because the
friction would cost more real votes than the cheating costs us. The real
defense is the curated ballot: every option is a film we already approved,
so a stuffed ballot still returns something we are happy to screen.

What IS hard: a poll accepts writes only while open and inside its
opens_at/closes_at window, and one email address gets one vote per poll
(a database constraint, see cinema/models/poll.py). That is the only
per-voter rule: there is no cookie, so a household sharing one computer
can each vote, and no per-IP cap, because the only address we can see
past the proxy is X-Forwarded-For, which the client writes.
"""

from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import IntegrityError, transaction

from .models import Vote


class VoteError(Exception):
    """Base for every refusal to record a vote."""


class PollNotOpen(VoteError):
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


def cast_vote(poll, option, email: str) -> Vote:
    """Record one vote, or raise a VoteError subclass explaining the refusal.

    The caller validates the address; a blank one is a programming error,
    not a refusal.
    """
    if not poll.is_accepting_votes():
        raise PollNotOpen(f"Poll {poll.pk} is not taking votes.")

    if option.poll_id != poll.pk:
        raise OptionMismatch("That option does not belong to this poll.")

    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email is required")

    if Vote.objects.filter(poll=poll, email=email).exists():
        raise EmailAlreadyVoted("This address has already voted in this poll.")

    try:
        with transaction.atomic():
            return Vote.objects.create(poll=poll, option=option, email=email)
    except IntegrityError as exc:
        # Two concurrent requests from the same address. The database
        # constraint is the authority; translate it into our own error.
        raise EmailAlreadyVoted("This address has already voted in this poll.") from exc
