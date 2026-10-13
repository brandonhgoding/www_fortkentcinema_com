"""Public-site cinema data, served from the native `cinema` ORM tables.

Reproduces the return shapes of the retired web/services/leprinceos.py (which
fetched the leprinceos HTTP API) so web/views.py and the templates are
unchanged. No request-time cache — reads the DB directly."""

import calendar
import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from cinema.models import Engagement, Showtime

from web.services.titles import listing_title

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
                {
                    "time": _format_showtime(st.starts_at),
                    "captions": st.captions or "",
                    "captions_label": st.get_captions_display() if st.captions else "",
                }
            )
        if not showtimes_by_date:
            continue
        movies.append(
            {
                "id": str(engagement.id),
                "title": pf.title if pf else "",
                "slug": (pf.slug if pf else "") or "",
                "rating": (pf.rating if pf else "") or "",
                "runtime": _format_runtime(pf.runtime_minutes if pf else None),
                "genre": "",
                # Wide viewports show this on the card itself (see
                # MovieCard.css). `description` is the film's own synopsis
                # with the TMDB overview as fallback, the same text the
                # /movies/<slug> page leads with.
                "synopsis": (pf.description if pf else "") or "",
                "poster": (pf.poster_url if pf else "") or "",
                "showtimes": showtimes_by_date,
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "is_free_for_members": bool(engagement.is_free_for_members),
                "language_label": engagement.language_label,
            }
        )
    return movies


def get_calendar_month(year, month):
    """Non-cancelled showtimes whose local day falls in the month, grouped by
    day-of-month (int), deduped per day by title. `month` is 0-based (0=Jan).
    Returns {} for an empty month.

    Only runs that were actually announced: a DRAFT booking's showtimes are
    not cancelled one by one, so without the status filter an unannounced
    booking would appear here. ENDED stays in, so past months still show
    what played."""
    cal_month = month + 1
    last_day = calendar.monthrange(year, cal_month)[1]
    start = timezone.make_aware(datetime.datetime(year, cal_month, 1, 0, 0, 0))
    end = timezone.make_aware(datetime.datetime(year, cal_month, last_day, 23, 59, 59))

    showtimes = (
        Showtime.objects.filter(is_cancelled=False, starts_at__gte=start, starts_at__lte=end)
        .filter(engagement__status__in=["CONFIRMED", "ENDED"])
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
                "slug": (pf.slug if pf else "") or "",
                "poster": (pf.poster_url if pf else "") or "",
                "youtube_id": (pf.youtube_id if pf else "") or "",
            }
        )
    return data


def get_coming_soon():
    """Confirmed engagements starting tomorrow+, deduped by film set (a double
    feature is a distinct set)."""
    today = timezone.localdate()
    tomorrow = today + datetime.timedelta(days=1)

    engagements = (
        Engagement.objects.filter(status="CONFIRMED", start_date__gte=tomorrow)
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
                "title": listing_title(
                    engagement.display_title or (pf.title if pf else "")
                ),
                "slug": (pf.slug if pf else "") or "",
                "start_date": engagement.start_date.isoformat(),
                "release_date": engagement.start_date.strftime("%B %-d"),
                "genre": "",
                "poster": (pf.poster_url if pf else "") or "",
                "films": [
                    {"id": f.id, "title": f.title, "slug": f.slug, "poster": f.poster_url}
                    for f in films
                ],
                "description": (pf.synopsis if pf else "") or "",
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "is_free_for_members": bool(engagement.is_free_for_members),
            }
        )
    return movies


def get_film_page(film):
    """Everything the /movies/<slug> page needs, from this cinema's own data.

    The film's *local* engagement history is the point: the synopsis/overview is
    the TMDB blurb that every other cinema site also publishes, so the showtimes
    and run dates are the only content here that is genuinely ours.

    Returns {"upcoming": [{date, display_date, showtimes: [...]}, ...],
             "runs": [{start_date, end_date, display_range, is_current}, ...],
             "language_labels": ["French · English subtitles", ...]}
    `language_labels` covers only runs with showtimes still to come.
    `upcoming` is empty for an archive film — the template must not fake it.
    """
    now = timezone.now()
    today = timezone.localdate()

    engagements = (
        film.engagements.filter(status="CONFIRMED")
        .prefetch_related("showtimes")
        .order_by("-start_date")
    )

    by_date = {}
    language_labels = []
    for engagement in engagements:
        upcoming_showtimes = engagement.showtimes.filter(
            is_cancelled=False, starts_at__gte=now
        )
        label = engagement.language_label
        if label and label not in language_labels and upcoming_showtimes:
            language_labels.append(label)
        for st in upcoming_showtimes:
            local = st.starts_at.astimezone(CINEMA_TZ)
            slot = by_date.setdefault(
                local.date(),
                {
                    "date": local.date().isoformat(),
                    "display_date": local.strftime("%A, %B %-d"),
                    "showtimes": [],
                },
            )
            slot["showtimes"].append(
                {
                    "time": _format_showtime(st.starts_at),
                    # Offset-aware ISO-8601 for schema.org ScreeningEvent.startDate.
                    "iso": local.isoformat(),
                    "screen": st.screen.name,
                    "captions": st.captions or "",
                    "captions_label": st.get_captions_display() if st.captions else "",
                    "format": engagement.get_presentation_format_display(),
                    "is_free_for_members": bool(engagement.is_free_for_members),
                }
            )

    upcoming = [by_date[d] for d in sorted(by_date)]

    runs = [
        {
            "start_date": e.start_date.isoformat(),
            "end_date": e.end_date.isoformat(),
            "display_range": _format_date_range(e.start_date, e.end_date),
            "is_current": e.start_date <= today <= e.end_date,
        }
        for e in engagements
    ]

    return {"upcoming": upcoming, "runs": runs, "language_labels": language_labels}


def _format_date_range(start, end):
    """'October 3–9, 2025', collapsing the month when it doesn't change."""
    if start == end:
        return start.strftime("%B %-d, %Y")
    if start.year == end.year and start.month == end.month:
        return f"{start.strftime('%B %-d')}–{end.strftime('%-d, %Y')}"
    if start.year == end.year:
        return f"{start.strftime('%B %-d')}–{end.strftime('%B %-d, %Y')}"
    return f"{start.strftime('%B %-d, %Y')}–{end.strftime('%B %-d, %Y')}"
