"""Craft Cinema Night: which dates it falls on, and what plays on them.

The night is "the last Tuesday of the month", which is a rule, not a list.
A typed list of dates is a list that goes stale in public, and it goes stale
SILENTLY — nothing breaks when the last one passes, the page just quietly
stops having a next date. So every date here is computed from the calendar.

What plays is not ours to type either. Craft Cinema Night takes whatever is
already in the evening slot that Tuesday, so the film comes out of the same
Engagement and Showtime rows Now Showing reads. The page and the schedule
cannot disagree, and nobody has to remember to update this file.

The catch that shapes everything below: bookings land two or three weeks
ahead, and the last Tuesday of the month is up to five weeks out. MOST
craft nights on this page will have no film yet, and that is the normal
state, not an error. A night with nothing booked returns film=None and the
template says so, rather than the page hiding the date or inventing a title.
"""
import calendar
import datetime

from cinema.models import Showtime
from web.constants import CRAFT_NIGHT
from web.services.cinema_data import _format_runtime, _format_showtime, _local_date
from web.services.showtimes import CINEMA_TZ


def last_tuesday(year, month):
    """The date of the last Tuesday in the given month."""
    weeks = calendar.monthcalendar(year, month)
    tuesdays = [week[calendar.TUESDAY] for week in weeks if week[calendar.TUESDAY]]
    return datetime.date(year, month, tuesdays[-1])


def upcoming_nights(count=None, *, today=None):
    """The next `count` craft nights, today's included if today is one.

    Today counts because the page is read during the day of the event — a
    6:30 PM show is still upcoming at noon. Rolling over at midnight rather
    than at showtime keeps this a date question, which is the only thing the
    rest of the page needs it to be.
    """
    if count is None:
        count = CRAFT_NIGHT["months_ahead"]
    if today is None:
        today = datetime.datetime.now(CINEMA_TZ).date()

    nights = []
    year, month = today.year, today.month
    while len(nights) < count:
        night = last_tuesday(year, month)
        if night >= today:
            nights.append(night)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return nights


def evening_showtimes(dates):
    """{date: Showtime} — the first evening performance on each of `dates`.

    One query for the whole span, bucketed in Python, the same shape
    get_calendar_month() uses. Filtering per date would be `count` queries
    for a page that renders six rows.

    "Evening" is a time-of-day floor rather than the exact advertised start:
    if a Tuesday's show moves to 7:00 the page should follow it, not go
    blank because 18:30 matched nothing.
    """
    if not dates:
        return {}

    start = datetime.datetime.combine(
        min(dates), datetime.time.min, tzinfo=CINEMA_TZ
    )
    end = datetime.datetime.combine(max(dates), datetime.time.max, tzinfo=CINEMA_TZ)

    wanted = set(dates)
    found = {}
    showtimes = (
        Showtime.objects.filter(
            is_cancelled=False,
            engagement__status="CONFIRMED",
            starts_at__gte=start,
            starts_at__lte=end,
        )
        .exclude(engagement__show_in_main_listings=False)
        # select_related for the engagement itself — prefetch_related does
        # not cover a forward FK, and without this each row re-fetches its
        # engagement when the lineup is built.
        .select_related("engagement")
        .prefetch_related("engagement__engagement_films__film")
        .order_by("starts_at")
    )
    for showtime in showtimes:
        local = _local_date(showtime.starts_at)
        if local not in wanted or local in found:
            continue
        local_time = showtime.starts_at.astimezone(CINEMA_TZ).time()
        if local_time < CRAFT_NIGHT["evening_from"]:
            continue
        found[local] = showtime
    return found


def get_craft_nights(count=None, *, today=None):
    """The upcoming craft nights, each with its film when one is booked."""
    nights = upcoming_nights(count, today=today)
    showtimes = evening_showtimes(nights)

    rows = []
    for night in nights:
        showtime = showtimes.get(night)
        film = None
        if showtime is not None:
            engagement = showtime.engagement
            primary = engagement.primary_film
            film = {
                "title": engagement.display_title or (primary.title if primary else ""),
                "slug": (primary.slug if primary else "") or "",
                "poster": (primary.poster_url if primary else "") or "",
                "rating": (primary.rating if primary else "") or "",
                "runtime": _format_runtime(
                    primary.runtime_minutes if primary else None
                ),
                # The real start, not the advertised one. If the schedule
                # moved this Tuesday's show, the page moves with it.
                "time": _format_showtime(showtime.starts_at),
            }
        rows.append(
            {
                "date": night,
                "iso": night.isoformat(),
                # "Tuesday, September 29" — no year. Every date here is
                # inside the next six months, so the year is noise.
                "label": night.strftime("%A, %B %-d"),
                "film": film,
            }
        )
    return rows
