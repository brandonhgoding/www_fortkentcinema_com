"""Public-site cinema data, served from the native `cinema` ORM tables.

Reproduces the return shapes of the retired web/services/leprinceos.py (which
fetched the leprinceos HTTP API) so web/views.py and the templates are
unchanged. No request-time cache — reads the DB directly."""

import calendar
import datetime

from django.utils import timezone

from cinema.dates import CINEMA_TZ, format_showtime
from cinema.models import Engagement, Showtime

from web.services.titles import listing_title

OPEN_CAPTIONS_NOTE = "This showing will be played with open captions."


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
                    "showtime_id": st.pk,
                    "time": format_showtime(st.starts_at),
                    # Offset-aware ISO-8601 for the home page's schema.org
                    # ScreeningEvent.startDate (partials/home_jsonld.html).
                    "iso": st.starts_at.astimezone(CINEMA_TZ).isoformat(),
                    "captions": st.captions or "",
                    "captions_label": st.get_captions_display() if st.captions else "",
                    # Open captions are burned into the picture, so the whole
                    # room reads them: worth a sentence, not a two-letter chip.
                    "captions_note": OPEN_CAPTIONS_NOTE if st.captions == "OC" else "",
                }
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
                # Wide viewports show this on the card itself (see
                # MovieCard.css). `description` is the film's own synopsis
                # with the TMDB overview as fallback.
                "synopsis": (pf.description if pf else "") or "",
                "poster": (pf.poster_url if pf else "") or "",
                "showtimes": showtimes_by_date,
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "is_free_for_members": bool(engagement.is_free_for_members),
                "language_label": engagement.language_label,
            }
        )
    return movies


def _hero_backdrop(url):
    """TMDB stores the w780 cut, which is soft stretched across a 1400px
    fold; ask for w1280 instead. Any other host's URL is left as it is."""
    if "image.tmdb.org" not in url:
        return url
    return url.replace("/t/p/w780/", "/t/p/w1280/")


def get_featured_showtime(now=None):
    """The home hero's showing: the next non-cancelled showtime that has not
    started, from the same pool get_now_showing() lists (confirmed, shown in
    the main listings, within the week), so the hero never names a film the
    listings below it do not. None when nothing is booked."""
    if now is None:
        now = timezone.now()
    today = _local_date(now)
    week_out = today + datetime.timedelta(days=7)
    showtime = (
        Showtime.objects.filter(
            is_cancelled=False,
            starts_at__gte=now,
            engagement__status="CONFIRMED",
            engagement__show_in_main_listings=True,
            engagement__start_date__lte=week_out,
            engagement__end_date__gte=today,
        )
        .select_related("engagement")
        .prefetch_related("engagement__engagement_films__film")
        .order_by("starts_at", "pk")
        .first()
    )
    if showtime is None:
        return None
    engagement = showtime.engagement
    pf = engagement.primary_film
    return {
        "showtime_id": showtime.pk,
        "title": listing_title(engagement.title or (pf.title if pf else "")),
        "rating": (pf.rating if pf else "") or "",
        "runtime": _format_runtime(pf.runtime_minutes if pf else None),
        "description": (pf.description if pf else "") or "",
        "poster": (pf.poster_url if pf else "") or "",
        "backdrop": _hero_backdrop((pf.backdrop_url if pf else "") or ""),
        "date": _local_date(showtime.starts_at).isoformat(),
        "time": format_showtime(showtime.starts_at),
    }


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
        key = ",".join(str(i) for i in ids) if ids else engagement.title
        if key in seen:
            continue
        seen.add(key)

        pf = engagement.primary_film
        movies.append(
            {
                "id": str(engagement.id),
                "title": listing_title(
                    engagement.title or (pf.title if pf else "")
                ),
                "start_date": engagement.start_date.isoformat(),
                "release_date": engagement.start_date.strftime("%B %-d"),
                "genre": "",
                "poster": (pf.poster_url if pf else "") or "",
                "films": [
                    {"id": f.id, "title": f.title, "poster": f.poster_url}
                    for f in films
                ],
                "description": (pf.synopsis if pf else "") or "",
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "is_free_for_members": bool(engagement.is_free_for_members),
            }
        )
    return movies
