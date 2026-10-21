"""What the phone line says, as plain strings.

Nothing Twilio-specific lives here on purpose: the menu reads these aloud
today, and the Level 2 voice agent can hand the same text to a model later.
"""

import datetime
from collections.abc import Iterable

from cinema.dates import CINEMA_TZ, format_showtime
from cinema.models import EngagementStatus, Showtime
from django.db.models import QuerySet
from django.utils import timezone
from web.constants import SITE_CONFIG, TICKET_PRICES

WEBSITE = "fort kent cinema dot com"

# A show that starts after midnight belongs to the evening before it: a
# 12:00 AM screening is "tonight" to an 11:50 PM caller (the owner's call),
# so a day's showtimes run until this time the next morning.
LATE_SHOWS_UNTIL = datetime.time(5, 0)

# How long after a show starts it is still read out. Doors are open and
# trailers rolling, so a 7:10 caller for the 7:00 wants to hear it.
STARTED_GRACE = datetime.timedelta(minutes=15)


def _day_start(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time.min, tzinfo=CINEMA_TZ)


def _day_end(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(
        day + datetime.timedelta(days=1), LATE_SHOWS_UNTIL, tzinfo=CINEMA_TZ
    )


def _show_day(starts_at: datetime.datetime) -> datetime.date:
    """The day a show is listed under: its Eastern date, or the day before
    for an after-midnight show."""
    local = starts_at.astimezone(CINEMA_TZ)
    if local.time() < LATE_SHOWS_UNTIL:
        return local.date() - datetime.timedelta(days=1)
    return local.date()


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
        # Engagement.title joins a double feature with " + ", which is
        # for reading, not listening: say "and" instead.
        title = engagement.display_title or _spoken_list(
            [film.title for film in engagement.ordered_films]
        )
        if engagement.is_free_for_members:
            title += ", free for members,"
        times = _spoken_list([format_showtime(s.starts_at) for s in group])
        sentences.append(f"{title} at {times}.")
    return " ".join(sentences)


def _day_label(day: datetime.date, today: datetime.date) -> str:
    if day == today + datetime.timedelta(days=1):
        return "tomorrow"
    return f"{day:%A}, {day:%B} {day.day}"


def showtimes_speech(now: datetime.datetime | None = None) -> str:
    """Today's remaining showtimes, or — when there are none left — the next
    day that has any.

    Shows that started more than a few minutes ago are left out: someone
    calling at 8 PM wants the 9:00, not to hear about the 4:00 they missed.
    "Today" runs past midnight (LATE_SHOWS_UNTIL), so a late show is read
    with the evening it belongs to.
    """
    now = (now or timezone.now()).astimezone(CINEMA_TZ)
    today = now.date()
    today_start = _day_start(today)
    today_end = _day_end(today)

    upcoming = _public_showtimes().filter(starts_at__gte=now - STARTED_GRACE)
    todays = list(upcoming.filter(starts_at__lt=today_end))
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

    first_next = upcoming.filter(starts_at__gte=today_end).first()
    if first_next is None:
        return (
            f"{opener} We don't have any upcoming showtimes scheduled yet. "
            f"Please check {WEBSITE} for updates."
        )

    next_day = _show_day(first_next.starts_at)
    next_shows = upcoming.filter(
        starts_at__gte=_day_start(next_day), starts_at__lt=_day_end(next_day)
    )
    return (
        f"{opener} Our next showtimes are {_day_label(next_day, today)}: "
        f"{_describe(next_shows)}"
    )


def _clock(t: datetime.time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def hours_and_prices_speech() -> str:
    minutes = SITE_CONFIG["box_office"]["opens_before_show_minutes"]
    street = SITE_CONFIG["cinema"]["address"]["street"]
    p = TICKET_PRICES
    return (
        f"We're at {street} in Fort Kent, and the box office opens "
        f"{minutes} minutes before every show. "
        f"Tickets are ${p['adult']} for adults, ${p['senior']} for seniors, "
        f"and ${p['child']} for children. "
        f"Matinees, for shows starting at {_clock(p['matinee_until'])} or earlier, "
        f"are ${p['matinee']}. "
        f"Members pay ${p['member']} for any show, and some shows are free "
        f"for members. "
        f"You can also buy tickets ahead of time at {WEBSITE}."
    )
