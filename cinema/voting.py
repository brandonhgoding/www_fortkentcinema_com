"""Vote casting and its integrity rules.

The protection here is deliberately soft. A determined person can clear
cookies and vote again from a phone, and no CAPTCHA is used because the
friction would cost more real votes than the cheating costs us. The real
defense is the curated ballot: every option is a film we already approved,
so a stuffed ballot still returns something we are happy to screen.

What IS hard: a closed poll never accepts a write, and one browser gets one
vote per poll (a database constraint, see cinema/models/poll.py).
"""

import hashlib
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import IntegrityError, transaction

from .models import PollStatus, Vote

VOTER_COOKIE = "fkc_voter"
VOTER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year

# High enough that a family, the library, or UMFK's NAT are unaffected; low
# enough that scripting gets boring.
IP_VOTE_CAP = 5


class VoteError(Exception):
    """Base for every refusal to record a vote."""


class PollNotOpen(VoteError):
    pass


class AlreadyVoted(VoteError):
    pass


class IPCapReached(VoteError):
    pass


class OptionMismatch(VoteError):
    pass


def hash_ip(ip: str | None) -> str:
    """Salted hash of an address. We never store the raw value."""
    if not ip:
        return ""
    salted = f"{settings.SECRET_KEY}:{ip}".encode()
    return hashlib.sha256(salted).hexdigest()


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


def cast_vote(poll, option, voter_key: str, ip: str | None = None) -> Vote:
    """Record one vote, or raise a VoteError subclass explaining the refusal."""
    if poll.status != PollStatus.OPEN:
        raise PollNotOpen(f"Poll {poll.pk} is {poll.status}, not open.")

    if option.poll_id != poll.pk:
        raise OptionMismatch("That option does not belong to this poll.")

    if Vote.objects.filter(poll=poll, voter_key=voter_key).exists():
        raise AlreadyVoted("This browser has already voted in this poll.")

    ip_hash = hash_ip(ip)
    if ip_hash:
        seen = Vote.objects.filter(poll=poll, ip_hash=ip_hash).count()
        if seen >= IP_VOTE_CAP:
            raise IPCapReached("Too many votes from this connection.")

    try:
        with transaction.atomic():
            return Vote.objects.create(
                poll=poll, option=option, voter_key=voter_key, ip_hash=ip_hash
            )
    except IntegrityError as exc:
        # Two concurrent requests from the same browser. The database
        # constraint is the authority; translate it into our own error.
        raise AlreadyVoted("This browser has already voted in this poll.") from exc
