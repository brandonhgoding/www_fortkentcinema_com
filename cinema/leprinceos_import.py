from __future__ import annotations

import datetime

import requests
from django.db import transaction

from .models import Engagement, EngagementFilm, Film, Screen, Showtime

REQUEST_TIMEOUT = 15


def fetch_all(base_url: str, path: str, *, session=None) -> list[dict]:
    """GET base_url+path and follow DRF `next` pagination, returning all records.

    `session` is any object with a `.get(url, timeout=...)` method (a
    requests.Session in production, a mock in tests); defaults to `requests`.
    """
    client = session or requests
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    records: list[dict] = []
    while url:
        resp = client.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "results" in data:
            records.extend(data["results"])
            url = data.get("next")
        else:
            records.extend(data)
            url = None
    return records


def _parse_dt(value: str) -> datetime.datetime:
    # API sends ISO with an offset, e.g. "2026-02-01T19:30:00-05:00" -> aware.
    return datetime.datetime.fromisoformat(value)


def import_all(base_url, *, flush, capacity_default=1, session=None) -> dict[str, int]:
    """Wipe and rebuild the cinema tables from the leprinceos API. All-or-nothing.

    Raises ValueError if flush is not True (guards accidental data loss).
    """
    if not flush:
        raise ValueError("import_all requires flush=True (full wipe + fresh import).")

    films_raw = fetch_all(base_url, "/films/", session=session)
    engagements_raw = fetch_all(base_url, "/engagements/", session=session)
    showtimes_raw = fetch_all(base_url, "/showtimes/", session=session)

    counts = {"screens": 0, "films": 0, "engagements": 0, "engagement_films": 0, "showtimes": 0}

    with transaction.atomic():
        # 1. Flush child-first.
        Showtime.objects.all().delete()
        EngagementFilm.objects.all().delete()
        Engagement.objects.all().delete()
        Film.objects.all().delete()
        Screen.objects.all().delete()

        # 2. Screens reconstructed from FK refs in engagements + showtimes.
        screen_names: dict[int, str] = {}
        for e in engagements_raw:
            if e.get("screen") is not None:
                screen_names.setdefault(e["screen"], e.get("screen_name") or f"Screen {e['screen']}")
        for s in showtimes_raw:
            if s.get("screen") is not None:
                screen_names.setdefault(s["screen"], s.get("screen_name") or f"Screen {s['screen']}")
        screen_map: dict[int, Screen] = {}
        for sid, name in screen_names.items():
            screen_map[sid] = Screen.objects.create(name=name, capacity=capacity_default)
        counts["screens"] = len(screen_map)

        # 3. Films.
        film_map: dict[int, Film] = {}
        for f in films_raw:
            film_map[f["id"]] = Film.objects.create(
                title=f.get("title", ""),
                runtime_minutes=f.get("runtime_minutes"),
                rating=f.get("rating") or "",
                synopsis=f.get("synopsis") or "",
                poster_url=f.get("poster_url") or "",
                backdrop_url=f.get("backdrop_url") or "",
                overview=f.get("overview") or "",
                tmdb_id=f.get("tmdb_id") or "",
                imdb_id=f.get("imdb_id") or "",
                youtube_id=f.get("youtube_id") or "",
            )
        counts["films"] = len(film_map)

        # 4. Engagements + ordered EngagementFilm rows.
        eng_map: dict[int, Engagement] = {}
        for e in engagements_raw:
            screen = screen_map.get(e.get("screen"))
            if screen is None:
                continue
            eng = Engagement.objects.create(
                screen=screen,
                start_date=e["start_date"],
                end_date=e["end_date"],
                kind=e.get("kind", "REGULAR"),
                event_title=e.get("event_title") or "",
                presentation_format=e.get("presentation_format", "2d"),
                status=e.get("status", "DRAFT"),
                show_in_main_listings=bool(e.get("show_in_main_listings", True)),
                notes=e.get("notes") or "",
            )
            eng_map[e["id"]] = eng
            counts["engagements"] += 1
            for pos, f in enumerate(e.get("films") or [], start=1):
                film = film_map.get(f["id"])
                if film is None:
                    continue
                EngagementFilm.objects.create(engagement=eng, film=film, position=pos)
                counts["engagement_films"] += 1

        # 5. Showtimes.
        for s in showtimes_raw:
            eng = eng_map.get(s.get("engagement"))
            screen = screen_map.get(s.get("screen"))
            if eng is None or screen is None:
                continue
            Showtime.objects.create(
                engagement=eng,
                screen=screen,
                starts_at=_parse_dt(s["starts_at"]),
                is_cancelled=bool(s.get("is_cancelled", False)),
                captions=s.get("captions") or None,
            )
            counts["showtimes"] += 1

    return counts
