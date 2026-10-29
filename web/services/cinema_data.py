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

# The ticket page's one-line note (tickets/views.py). The listing chips say
# OC with a spelled-out screen-reader label instead.
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
    HomeView._add_ticket_state() completes."""
    return {
        "showtime_id": st.pk,
        "time": format_showtime(st.starts_at),
        # Offset-aware ISO-8601 for the home page's schema.org
        # ScreeningEvent.startDate (partials/home_jsonld.html).
        "iso": st.starts_at.astimezone(CINEMA_TZ).isoformat(),
        "captions": st.captions or "",
        "captions_label": st.get_captions_display() if st.captions else "",
    }


def _hero_backdrop(url):
    """TMDB stores the w780 cut, which is soft stretched across a 1400px
    fold; ask for w1280 instead. Any other host's URL is left as it is."""
    if "image.tmdb.org" not in url:
        return url
    return url.replace("/t/p/w780/", "/t/p/w1280/")


def get_hero_films(now=None):
    """The home hero's films, which is the listing: every confirmed run shown
    in the main listings and within the week (the pool Now Showing had) with a
    non-cancelled showtime that has not started, in order of that next
    showing, so the fold opens on the next thing on and can switch to the
    rest. [] when nothing is booked.

    Each film carries `upcoming`: its own not-yet-started showtimes grouped
    by local date, every date of the week (the hero is the listing; the
    template folds rows past the third behind a toggle), each time in the
    chip shape (HomeView._add_ticket_state completes it); and `date`/`time`,
    its next showing, for the strip that names the films not on the fold.
    `youtube_id`, `language_label` and `is_free_for_members` are what the
    listing card used to carry."""
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
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "language_label": engagement.language_label,
                "is_free_for_members": bool(engagement.is_free_for_members),
            }
            by_date[st.engagement_id] = {}
        key = _local_date(st.starts_at).isoformat()
        by_date[st.engagement_id].setdefault(key, []).append(_time_entry(st))

    for pk, film in films.items():
        dates = by_date[pk]
        film["upcoming"] = [{"key": key, "times": dates[key]} for key in sorted(dates)]
    return list(films.values())


def get_calendar_month(year, month):
    """Non-cancelled showtimes whose local day falls in the month, grouped by
    day-of-month (int), deduped per day by title. `month` is 0-based (0=Jan).
    Returns {} for an empty month.

    Each day's film carries `times`: that day's showtimes for the title (two
    runs of one title on one day merge), in the chip shape, so a poster can
    open the day's times (CalendarMonthView completes the ticket state). A
    run hidden from the main listings keeps its poster but lists no times:
    its ticket page 404s them.

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
        movie = next((m for m in movies if m["title"] == title), None)
        if movie is None:
            movie = {
                "id": str(st.id),
                "title": title,
                "poster": (pf.poster_url if pf else "") or "",
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "times": [],
            }
            movies.append(movie)
        if st.engagement.show_in_main_listings:
            movie["times"].append(_time_entry(st))
    return data


def get_coming_soon(now=None):
    """Confirmed engagements starting tomorrow+, deduped by film set (a double
    feature is a distinct set).

    Each card carries `upcoming`: the not-yet-started, non-cancelled showtimes
    of every run the card stands for (runs of one film set collapse into one
    card, so their showtimes merge), grouped by local date, each time in the
    chip shape (HomeView._add_ticket_state completes it). That is how a run
    beyond the hero's week sells tickets. [] when none are entered yet."""
    if now is None:
        now = timezone.now()
    today = _local_date(now)
    tomorrow = today + datetime.timedelta(days=1)

    engagements = (
        Engagement.objects.filter(status="CONFIRMED", start_date__gte=tomorrow)
        .prefetch_related("engagement_films__film")
        .order_by("start_date")
    )

    cards = {}
    runs_by_key = {}
    for engagement in engagements:
        films = engagement.ordered_films
        ids = sorted(f.id for f in films)
        key = ",".join(str(i) for i in ids) if ids else engagement.title
        runs_by_key.setdefault(key, []).append(engagement.pk)
        if key in cards:
            continue

        pf = engagement.primary_film
        cards[key] = (
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

    by_run = _upcoming_by_engagement(
        [pk for pks in runs_by_key.values() for pk in pks], now
    )
    for key, card in cards.items():
        dates = {}
        for pk in runs_by_key[key]:
            for date_key, times in by_run.get(pk, {}).items():
                dates.setdefault(date_key, []).extend(times)
        card["upcoming"] = [
            {"key": date_key, "times": dates[date_key]} for date_key in sorted(dates)
        ]
    return list(cards.values())


def _upcoming_by_engagement(engagement_ids, now):
    """engagement pk -> {local date iso -> [chip-shaped times]} for the
    not-yet-started, non-cancelled showtimes of those runs, one query. A run
    hidden from the main listings keeps its card but lists no showtimes: the
    ticket page 404s them, as the hero and the phone line leave them out."""
    showtimes = Showtime.objects.filter(
        engagement_id__in=engagement_ids,
        engagement__show_in_main_listings=True,
        is_cancelled=False,
        starts_at__gte=now,
    ).order_by("starts_at", "pk")
    out = {}
    for st in showtimes:
        dates = out.setdefault(st.engagement_id, {})
        dates.setdefault(_local_date(st.starts_at).isoformat(), []).append(
            _time_entry(st)
        )
    return out
