"""Public-site cinema data, served from the native `cinema` ORM tables.

Reproduces the return shapes of the retired web/services/leprinceos.py (which
fetched the leprinceos HTTP API) so web/views.py and the templates are
unchanged. No request-time cache — reads the DB directly."""

import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from cinema.models import Engagement

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
