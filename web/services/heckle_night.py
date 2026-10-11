"""Heckle Night: which dates it falls on, and what plays on them.

Structurally the twin of web/services/craft_night.py, and for the same two
reasons. The night is "the third Friday of the month", which is a rule, not
a list — a typed list of dates goes stale in public and goes stale SILENTLY,
because nothing breaks when the last one passes, the page just quietly stops
having a next date. And what plays is not ours to type either: the film comes
out of the same Engagement and Showtime rows Now Showing reads, so the page
and the schedule cannot disagree.

Where it DIVERGES from craft night, and this is the important difference:
craft night adopts whatever regular show is already in that Tuesday's
evening slot — that is its whole premise, a normal screening run a little
differently. Heckle Night is not a normal screening. It is its own booking,
so the lineup query matches Engagement.Kind.SPECIAL_EVENT only. Without
that filter the page would cheerfully announce the Friday first-run feature
as the film the room is invited to shout at.

The same reasoning is why the start time is matched exactly rather than as
a floor. Craft night's floor exists because a regular show may move and the
page should follow it. Heckle Night follows nothing: it is the 7:00 PM
special event on the third Friday, and anything else that day is somebody
else's screening. Crude, and deliberately so — see the note on
HECKLE_NIGHT["start_time"] for what it costs and what would replace it.

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

from cinema.models import Engagement, Showtime
from web.constants import HECKLE_NIGHT
from web.services.cinema_data import _format_runtime, _format_showtime, _local_date
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
    """{date: Showtime} — the 7:00 PM SPECIAL EVENT on each of `dates`.

    One query for the whole span, bucketed in Python, the same shape
    get_calendar_month() and craft night use. Filtering per date would be
    `count` queries for a page that renders six rows.

    SPECIAL_EVENT and nothing else. A first-run feature in the Friday
    evening slot is not Heckle Night and must never be announced as it,
    which is what an unfiltered query did. CLASSIC and DOUBLE_FEATURE are
    deliberately NOT matched either: a Heckle Night booking has one kind,
    so a night booked as something else shows "Not booked yet" — visibly
    wrong on the page — rather than quietly adopting the wrong film.

    show_in_main_listings survives the change and is now carrying the
    privacy guard on its own. Special events are the shape a private
    booking takes, and unticking that box is how one is marked private;
    a page that advertised those would be leaking them. Booked in the
    dashboard the box defaults to on, so a public Heckle Night needs
    nothing done to it — only a private event needs the box cleared.
    (Engagement.default_visibility_for() would default special events to
    hidden, but only the backfill command consults it, not the form.)

    The time is matched EXACTLY, not as a floor. A Heckle Night is the
    7:00 PM event on the third Friday; a special event at any other time
    that day is a different night and this page will not claim it. That
    is crude on purpose and the cost is known: a Heckle Night booked for
    7:30 makes this page say "Not booked yet" while the listings show the
    event. It fails visibly rather than silently, which is the same trade
    the SPECIAL_EVENT filter makes, and the honest fix is a flag on the
    Engagement rather than a cleverer query.

    Note this is the opposite of craft_night.evening_showtimes(), which
    uses a floor precisely BECAUSE it adopts a regular show and a regular
    show is allowed to move. Heckle Night adopts nothing.
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
            engagement__kind=Engagement.Kind.SPECIAL_EVENT,
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
        if local_time != HECKLE_NIGHT["start_time"]:
            continue
        found[local] = showtime
    return found


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
                    engagement.display_title or (primary.title if primary else "")
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
                "time": _format_showtime(showtime.starts_at),
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
