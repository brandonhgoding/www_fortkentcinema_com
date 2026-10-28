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


def _time_entry(st):
    """One listed showtime, the shape partials/showtime_chip.html reads and
    HomeView._add_ticket_state() completes. Shared by the Now Showing cards
    and the hero's own rows so a time cannot look different in the two."""
    return {
        "showtime_id": st.pk,
        "time": format_showtime(st.starts_at),
        # Offset-aware ISO-8601 for the home page's schema.org
        # ScreeningEvent.startDate (partials/home_jsonld.html).
        "iso": st.starts_at.astimezone(CINEMA_TZ).isoformat(),
        "captions": st.captions or "",
        "captions_label": st.get_captions_display() if st.captions else "",
        # Open captions are burned into the picture, so the whole room reads
        # them: worth a sentence, not a two-letter chip.
        "captions_note": OPEN_CAPTIONS_NOTE if st.captions == "OC" else "",
    }


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
            showtimes_by_date.setdefault(local_date, []).append(_time_entry(st))
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


# Dates the hero lists for each film. Beyond these the visitor is one click
# from the full schedule, and a fourth row pushes the buttons off a phone's
# first screen.
HERO_DATES = 3


def get_hero_films(now=None):
    """The home hero's films: every film in the pool get_now_showing() lists
    (confirmed, shown in the main listings, within the week) with a
    non-cancelled showtime that has not started, in order of that next
    showing, so the fold opens on the next thing on and can switch to the
    rest. [] when nothing is booked.

    Each film carries `upcoming`: its own not-yet-started showtimes grouped
    by local date, the first HERO_DATES dates, each time in the chip shape
    (HomeView._add_ticket_state completes it); and `date`/`time`, its next
    showing, for the strip that names the films not on the fold."""
    if now is None:
        now = timezone.now()
    today = _local_date(now)
    week_out = today + datetime.timedelta(days=7)
    showtimes = (
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
    )

    films = {}
    by_date = {}
    for st in showtimes:
        if st.engagement_id not in films:
            engagement = st.engagement
            pf = engagement.primary_film
            films[st.engagement_id] = {
                "id": str(engagement.pk),
                "showtime_id": st.pk,
                "title": listing_title(engagement.title or (pf.title if pf else "")),
                "rating": (pf.rating if pf else "") or "",
                "runtime": _format_runtime(pf.runtime_minutes if pf else None),
                "description": (pf.description if pf else "") or "",
                "poster": (pf.poster_url if pf else "") or "",
                "backdrop": _hero_backdrop((pf.backdrop_url if pf else "") or ""),
                "date": _local_date(st.starts_at).isoformat(),
                "time": format_showtime(st.starts_at),
            }
            by_date[st.engagement_id] = {}
        key = _local_date(st.starts_at).isoformat()
        by_date[st.engagement_id].setdefault(key, []).append(_time_entry(st))

    for pk, film in films.items():
        dates = by_date[pk]
        film["upcoming"] = [
            {"key": key, "times": dates[key]} for key in sorted(dates)[:HERO_DATES]
        ]
    return list(films.values())


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
