"""What the phone line says, as plain strings.

Nothing Twilio-specific lives here on purpose: the menu reads these aloud
today, and the Level 2 voice agent can hand the same text to a model later.
"""

import datetime
from collections.abc import Iterable

from cinema.models import EngagementStatus, Showtime
from django.db.models import QuerySet
from django.utils import timezone
from web.constants import SITE_CONFIG, TICKET_PRICES
from web.services.cinema_data import _format_showtime

WEBSITE = "fort kent cinema dot com"


def _day_start(day: datetime.date) -> datetime.datetime:
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))


def _public_showtimes() -> QuerySet[Showtime]:
    """Showtimes a caller may be told about: the same rule as Now Showing on
    the home page (confirmed, not hidden from listings, not cancelled)."""
    return (
        Showtime.objects.filter(
            is_cancelled=False, engagement__status=EngagementStatus.CONFIRMED
        )
        .exclude(engagement__show_in_main_listings=False)
        .select_related("engagement")
        .prefetch_related("engagement__engagement_films__film")
        .order_by("starts_at")
    )


def _spoken_list(items: list[str]) -> str:
    """["a"] -> "a"; ["a", "b"] -> "a and b"; ["a", "b", "c"] -> "a, b, and c"."""
    if len(items) <= 2:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _describe(showtimes: Iterable[Showtime]) -> str:
    """One sentence per title, in order of its first show:
    "Hamnet at 4:00 PM and 7:15 PM. Weapons, free for members, at 7:00 PM."
    """
    by_engagement: dict[int, list[Showtime]] = {}
    for showtime in showtimes:
        by_engagement.setdefault(showtime.engagement.pk, []).append(showtime)

    sentences = []
    for group in by_engagement.values():
        engagement = group[0].engagement
        title = engagement.display_title
        if engagement.is_free_for_members:
            title += ", free for members,"
        times = _spoken_list([_format_showtime(s.starts_at) for s in group])
        sentences.append(f"{title} at {times}.")
    return " ".join(sentences)


def _day_label(day: datetime.date, today: datetime.date) -> str:
    if day == today + datetime.timedelta(days=1):
        return "tomorrow"
    return f"{day:%A}, {day:%B} {day.day}"


def showtimes_speech(now: datetime.datetime | None = None) -> str:
    """Today's remaining showtimes, or — when there are none left — the next
    day that has any.

    Shows that have already started are left out: someone calling at 8 PM
    wants the 9:00, not to hear about the 4:00 they missed.
    """
    now = timezone.localtime(now)
    today = now.date()
    today_start = _day_start(today)
    tomorrow_start = _day_start(today + datetime.timedelta(days=1))

    upcoming = _public_showtimes().filter(starts_at__gte=now)
    todays = list(upcoming.filter(starts_at__lt=tomorrow_start))
    if todays:
        return f"Today's showtimes: {_describe(todays)}"

    played_today = (
        _public_showtimes()
        .filter(starts_at__gte=today_start, starts_at__lt=now)
        .exists()
    )
    opener = (
        "There are no more shows today."
        if played_today
        else "There are no shows today."
    )

    first_next = upcoming.filter(starts_at__gte=tomorrow_start).first()
    if first_next is None:
        return (
            f"{opener} We don't have any upcoming showtimes scheduled yet. "
            f"Please check {WEBSITE} for updates."
        )

    next_day = timezone.localtime(first_next.starts_at).date()
    next_shows = upcoming.filter(
        starts_at__gte=_day_start(next_day),
        starts_at__lt=_day_start(next_day + datetime.timedelta(days=1)),
    )
    return (
        f"{opener} Our next showtimes are {_day_label(next_day, today)}: "
        f"{_describe(next_shows)}"
    )


def _clock(t: datetime.time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def hours_and_prices_speech() -> str:
    hours = _spoken_list(
        [
            f"{block['days'].replace(' - ', ' through ')}, "
            f"{block['open']} to {block['close']}"
            for block in SITE_CONFIG["hours"].values()
        ]
    )
    street = SITE_CONFIG["cinema"]["address"]["street"]
    p = TICKET_PRICES
    return (
        f"We're at {street} in Fort Kent, and we're open {hours}. "
        f"Tickets are ${p['adult']} for adults, ${p['senior']} for seniors, "
        f"and ${p['child']} for children. "
        f"Matinees, for shows starting at {_clock(p['matinee_until'])} or earlier, "
        f"are ${p['matinee']}. "
        f"Members pay ${p['member']} for any show, and some shows are free "
        f"for members."
    )
