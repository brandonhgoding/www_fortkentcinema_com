"""Server-side port of the SPA's src/services/api.js for the leprinceos
(cinema_sass) API. Fetches engagements/showtimes/films, converts UTC times to
America/New_York, and caches results with a stale-on-failure fallback."""

import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache

CINEMA_TZ = ZoneInfo("America/New_York")
BASE_URL = settings.LEPRINCEOS_BASE_URL


def _get(path, ttl=180):
    """GET BASE_URL+path, unwrap DRF 'results', cache for `ttl`s with a
    no-expiry stale copy served if a later refetch fails."""
    key = f"lpos:{path}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = requests.get(BASE_URL + path, timeout=4)
        resp.raise_for_status()
        data = resp.json()
        results = (
            data["results"] if isinstance(data, dict) and "results" in data else data
        )
        cache.set(key, results, ttl)
        cache.set(f"{key}:stale", results, None)
        return results
    except Exception:
        stale = cache.get(f"{key}:stale")
        return stale if stale is not None else []


def _format_showtime(utc_iso):
    dt = datetime.datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).astimezone(
        CINEMA_TZ
    )
    # e.g. "6:00 PM" — strip leading zero on the hour
    return dt.strftime("%I:%M %p").lstrip("0")


def _local_date(utc_iso):
    dt = datetime.datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).astimezone(
        CINEMA_TZ
    )
    return dt.date().isoformat()


def _format_runtime(minutes):
    if not minutes:
        return ""
    h, m = divmod(int(minutes), 60)
    if h == 0:
        return f"{m}min"
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}min"


def _primary_film_id(engagement):
    films = engagement.get("films") or []
    return films[0]["id"] if films else None


def get_now_showing():
    """Port of api.js getNowShowing(): confirmed engagements active in the next
    7 days, each with its showtimes grouped by local date. Returns only movies
    with at least one upcoming showtime date."""
    now = datetime.datetime.now(CINEMA_TZ)
    today = now.date().isoformat()
    seven_days_str = (now + datetime.timedelta(days=7)).date().isoformat()

    # Fetch confirmed engagements active within the next 7 days
    engagements = _get(
        f"/engagements/?status=CONFIRMED&start_date_before={seven_days_str}"
        f"&end_date_after={today}"
    )

    # Include every category (REGULAR, DOUBLE_FEATURE, CLASSIC, ...) but drop
    # engagements explicitly hidden from the main listings.
    visible_engagements = [
        e for e in engagements if e.get("show_in_main_listings") is not False
    ]

    if not visible_engagements:
        return []

    movies = []
    for engagement in visible_engagements:
        # Fetch showtimes — this is the critical data
        showtimes = _get(
            f"/showtimes/?engagement={engagement['id']}&is_cancelled=false"
        )

        # Fetch film details separately — optional, for rating/runtime
        film = None
        lead_id = _primary_film_id(engagement)
        if lead_id is not None:
            film = _get(f"/films/{lead_id}/")

        # Group showtimes by local date
        showtimes_by_date = {}
        for st in showtimes:
            local_date = _local_date(st["starts_at"])
            local_time = _format_showtime(st["starts_at"])
            showtimes_by_date.setdefault(local_date, []).append(local_time)

        movies.append(
            {
                "id": str(engagement["id"]),
                "title": engagement.get("film_title"),
                "rating": (film or {}).get("rating") or "",
                "runtime": _format_runtime((film or {}).get("runtime_minutes")),
                "genre": "",
                "poster": engagement.get("film_poster_url")
                or (film or {}).get("poster_url")
                or "",
                "showtimes": showtimes_by_date,
                "youtube_id": (film or {}).get("youtube_id") or "",
                "is_free_for_members": bool(engagement.get("is_free_for_members")),
            }
        )

    # Filter out engagements that have no upcoming showtimes
    return [m for m in movies if m["showtimes"]]


def get_coming_soon():
    """Port of api.js getComingSoon(): confirmed engagements starting tomorrow+,
    deduped by film set, kind != CLASSIC."""
    now = datetime.datetime.now(CINEMA_TZ)
    tomorrow_str = (now + datetime.timedelta(days=1)).date().isoformat()

    # Fetch confirmed engagements that start tomorrow or later
    engagements = _get(
        f"/engagements/?status=CONFIRMED&start_date_after={tomorrow_str}"
    )

    if not engagements:
        return []

    # Deduplicate by film set (same film(s) may have multiple future
    # engagements; a double feature is a distinct set). Classic screenings
    # have their own /classics page, so keep them out of Coming Soon.
    seen_films = set()
    unique_engagements = []
    for e in engagements:
        if e.get("kind") == "CLASSIC":
            continue
        films = e.get("films") or []
        ids = sorted(f["id"] for f in films)
        key = ",".join(str(i) for i in ids) if ids else e.get("film_title")
        if key in seen_films:
            continue
        seen_films.add(key)
        unique_engagements.append(e)

    # Fetch film details for extra metadata
    movies = []
    for engagement in unique_engagements:
        film = None
        lead_id = _primary_film_id(engagement)
        if lead_id is not None:
            film = _get(f"/films/{lead_id}/")

        release_date = datetime.date.fromisoformat(engagement["start_date"])
        formatted_date = release_date.strftime("%B %-d")

        films = engagement.get("films") or []

        movies.append(
            {
                "id": str(engagement["id"]),
                "title": engagement.get("display_title")
                or engagement.get("film_title"),
                "start_date": engagement.get("start_date"),
                "release_date": formatted_date,
                "genre": "",
                "poster": engagement.get("film_poster_url")
                or (film or {}).get("poster_url")
                or "",
                "films": [
                    {
                        "id": f["id"],
                        "title": f.get("title"),
                        "poster": f.get("poster_url"),
                    }
                    for f in films
                ],
                "description": (film or {}).get("synopsis") or "",
                "youtube_id": (film or {}).get("youtube_id") or "",
                "is_free_for_members": bool(engagement.get("is_free_for_members")),
            }
        )

    return movies
