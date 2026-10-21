"""Heckle Night: which dates it falls on, and what plays on them.

Structurally the twin of the old craft night service, and for the same two
reasons. The night is "the third Friday of the month", which is a rule, not
a list — a typed list of dates goes stale in public and goes stale SILENTLY,
because nothing breaks when the last one passes, the page just quietly stops
having a next date. And what plays will not be ours to type either: once the
Event model lands, the film will come out of the same rows Now Showing
reads, so the page and the schedule cannot disagree.

The film lookup is parked until the Event model exists, so every night
reads "Not booked yet". The dates still compute.

The one thing craft night did not need is a start date. Craft night was
already running when its page shipped; this one has never run, and the rule
on its own would happily advertise a third Friday that nobody has planned.
HECKLE_NIGHT["starts_on"] is the floor, and no date before it is a heckle
night no matter what the calendar says.

Everything else follows craft night's shape, including the consequence that
MOST listed nights have no film yet — bookings land two or three weeks out
and the sixth Friday on this page is five months out. A night with nothing
booked returns film=None and the template says so, rather than hiding the
date or inventing a title.
"""
import calendar
import datetime

from cinema.dates import format_showtime
from web.constants import HECKLE_NIGHT
from web.services.cinema_data import _format_runtime
from web.services.showtimes import CINEMA_TZ
from web.services.titles import event_page_title


def third_friday(year, month):
    """The date of the third Friday in the given month.

    Indexed off the Fridays that fall in the month rather than off "the
    15th, then forward", so a month beginning on a Friday counts that
    Friday as the first one — which is how everyone reads "third Friday".
    """
    weeks = calendar.monthcalendar(year, month)
    fridays = [week[calendar.FRIDAY] for week in weeks if week[calendar.FRIDAY]]
    return datetime.date(year, month, fridays[2])


def upcoming_nights(count=None, *, today=None):
    """The next `count` heckle nights, today's included if today is one.

    Today counts because the page is read during the day of the event — a
    7:00 PM show is still upcoming at noon. Rolling over at midnight rather
    than at showtime keeps this a date question, which is the only thing
    the rest of the page needs it to be.

    Nights before HECKLE_NIGHT["starts_on"] are not nights at all. Before
    the first one this walks forward to October; after it the floor never
    binds again and this behaves exactly like craft night's.
    """
    if count is None:
        count = HECKLE_NIGHT["months_ahead"]
    if today is None:
        today = datetime.datetime.now(CINEMA_TZ).date()

    floor = max(today, HECKLE_NIGHT["starts_on"])

    nights = []
    year, month = floor.year, floor.month
    while len(nights) < count:
        night = third_friday(year, month)
        if night >= floor:
            nights.append(night)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return nights


def heckle_showtimes(dates):
    """Interim: always empty.

    The lineup used to match the 7:00 PM Special Event on each date, and
    that kind no longer exists. The Event model replaces this lookup; until
    it lands every night reads "Not booked yet".
    """
    return {}


def get_heckle_nights(count=None, *, today=None):
    """The upcoming heckle nights, each with its film when one is booked."""
    nights = upcoming_nights(count, today=today)
    showtimes = heckle_showtimes(nights)

    rows = []
    for night in nights:
        showtime = showtimes.get(night)
        film = None
        if showtime is not None:
            engagement = showtime.engagement
            primary = engagement.primary_film
            film = {
                "title": event_page_title(
                    engagement.title or (primary.title if primary else "")
                ),
                "slug": (primary.slug if primary else "") or "",
                "poster": (primary.poster_url if primary else "") or "",
                "rating": (primary.rating if primary else "") or "",
                "runtime": _format_runtime(
                    primary.runtime_minutes if primary else None
                ),
                # Always HECKLE_NIGHT["start_label"] in practice, since
                # nothing else matches — formatted from the row rather
                # than the constant so the two cannot drift apart
                # unnoticed if the match ever loosens again.
                "time": format_showtime(showtime.starts_at),
            }
        rows.append(
            {
                "date": night,
                "iso": night.isoformat(),
                # "Friday, October 16" — no year. Every date here is inside
                # the next six months, so the year is noise.
                "label": night.strftime("%A, %B %-d"),
                "film": film,
            }
        )
    return rows
