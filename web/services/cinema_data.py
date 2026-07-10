"""Public-site cinema data, served from the native `cinema` ORM tables.

Reproduces the return shapes of the retired web/services/leprinceos.py (which
fetched the leprinceos HTTP API) so web/views.py and the templates are
unchanged. No request-time cache — reads the DB directly."""

import calendar
import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from cinema.models import Engagement, Showtime

CINEMA_TZ = ZoneInfo("America/New_York")


def _format_showtime(dt):
    # e.g. "6:00 PM" — strip the leading zero on the hour.
    return dt.astimezone(CINEMA_TZ).strftime("%I:%M %p").lstrip("0")


def _local_date(dt):
    return dt.astimezone(CINEMA_TZ).date()


def _format_runtime(minutes):
    if not minutes:
        return ""
    h, m = divmod(int(minutes), 60)
    if h == 0:
        return f"{m}min"
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}min"


def get_now_showing():
    """Confirmed, visible engagements active in the next 7 days, each with its
    non-cancelled showtimes grouped by local date. Only movies with at least
    one upcoming showtime date. Matches the old API-backed shape."""
    today = timezone.localdate()
    week_out = today + datetime.timedelta(days=7)

    engagements = (
        Engagement.objects.filter(
            status="CONFIRMED", start_date__lte=week_out, end_date__gte=today,
        )
        .exclude(show_in_main_listings=False)
        .prefetch_related("engagement_films__film")
    )

    movies = []
    for engagement in engagements:
        pf = engagement.primary_film
        showtimes_by_date = {}
        for st in engagement.showtimes.filter(is_cancelled=False):
            local_date = _local_date(st.starts_at).isoformat()
            showtimes_by_date.setdefault(local_date, []).append(
                _format_showtime(st.starts_at)
            )
        if not showtimes_by_date:
            continue
        movies.append(
            {
                "id": str(engagement.id),
                "title": pf.title if pf else "",
                "rating": (pf.rating if pf else "") or "",
                "runtime": _format_runtime(pf.runtime_minutes if pf else None),
                "genre": "",
                "poster": (pf.poster_url if pf else "") or "",
                "showtimes": showtimes_by_date,
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "is_free_for_members": bool(engagement.is_free_for_members),
            }
        )
    return movies


def get_calendar_month(year, month):
    """Non-cancelled showtimes whose local day falls in the month, grouped by
    day-of-month (int), deduped per day by title. `month` is 0-based (0=Jan).
    Returns {} for an empty month."""
    cal_month = month + 1
    last_day = calendar.monthrange(year, cal_month)[1]
    start = timezone.make_aware(datetime.datetime(year, cal_month, 1, 0, 0, 0))
    end = timezone.make_aware(datetime.datetime(year, cal_month, last_day, 23, 59, 59))

    showtimes = (
        Showtime.objects.filter(is_cancelled=False, starts_at__gte=start, starts_at__lte=end)
        .select_related("screen")
        .prefetch_related("engagement__engagement_films__film")
    )

    data = {}
    for st in showtimes:
        day = _local_date(st.starts_at).day
        pf = st.engagement.primary_film
        title = pf.title if pf else ""
        movies = data.setdefault(day, [])
        if any(m["title"] == title for m in movies):
            continue
        movies.append(
            {
                "id": str(st.id),
                "title": title,
                "poster": (pf.poster_url if pf else "") or "",
                "youtube_id": (pf.youtube_id if pf else "") or "",
            }
        )
    return data


def get_coming_soon():
    """Confirmed engagements starting tomorrow+, non-CLASSIC, deduped by film
    set (a double feature is a distinct set)."""
    today = timezone.localdate()
    tomorrow = today + datetime.timedelta(days=1)

    engagements = (
        Engagement.objects.filter(status="CONFIRMED", start_date__gte=tomorrow)
        .exclude(kind="CLASSIC")
        .prefetch_related("engagement_films__film")
        .order_by("start_date")
    )

    seen = set()
    movies = []
    for engagement in engagements:
        films = engagement.ordered_films
        ids = sorted(f.id for f in films)
        key = ",".join(str(i) for i in ids) if ids else engagement.display_title
        if key in seen:
            continue
        seen.add(key)

        pf = engagement.primary_film
        movies.append(
            {
                "id": str(engagement.id),
                "title": engagement.display_title or (pf.title if pf else ""),
                "start_date": engagement.start_date.isoformat(),
                "release_date": engagement.start_date.strftime("%B %-d"),
                "genre": "",
                "poster": (pf.poster_url if pf else "") or "",
                "films": [
                    {"id": f.id, "title": f.title, "poster": f.poster_url} for f in films
                ],
                "description": (pf.synopsis if pf else "") or "",
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "is_free_for_members": bool(engagement.is_free_for_members),
            }
        )
    return movies


def get_classic_movie_night():
    """Confirmed CLASSIC engagements still running or upcoming, expanded into
    one screening per non-cancelled future showtime, sorted by date. Returns
    {"next_screening": <dict|None>, "upcoming": [<dict>]}."""
    today = timezone.localdate()
    engagements = (
        Engagement.objects.filter(kind="CLASSIC", status="CONFIRMED", end_date__gte=today)
        .prefetch_related("engagement_films__film")
    )

    screenings = []
    for engagement in engagements:
        pf = engagement.primary_film
        title = engagement.display_title or (pf.title if pf else "")
        for st in engagement.showtimes.filter(is_cancelled=False):
            local = st.starts_at.astimezone(CINEMA_TZ)
            if local.date() < today:
                continue
            screenings.append(
                {
                    "id": str(st.id),
                    "title": title,
                    "poster": (pf.poster_url if pf else "") or "",
                    "rating": (pf.rating if pf else "") or "",
                    "runtime": _format_runtime(pf.runtime_minutes if pf else None),
                    "synopsis": (pf.synopsis if pf else "") or "",
                    "youtube_id": (pf.youtube_id if pf else "") or "",
                    "date": local.date().isoformat(),
                    "display_date": local.strftime("%A, %B %-d"),
                }
            )

    screenings.sort(key=lambda s: s["date"])
    return {
        "next_screening": screenings[0] if screenings else None,
        "upcoming": screenings[1:],
    }
