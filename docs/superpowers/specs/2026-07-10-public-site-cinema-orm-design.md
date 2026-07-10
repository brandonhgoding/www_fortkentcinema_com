# Public Site → cinema ORM (retire the leprinceos API) — Design

**Date:** 2026-07-10
**Status:** Awaiting user review (design phase)
**Repo:** `api_fortkentcinema_com` (branch: new `feat/public-cinema-orm`)

## Context

The public marketing site (`web` app) still renders its cinema data — **Now Showing** and **Coming Soon** on the home page, the **Calendar** month view, and the **Classics** page — by calling the leprinceos HTTP API at request time (`web/services/leprinceos.py`, consumed only by `web/views.py`). Now that the native `cinema` tables are the source of truth (populated by `import_leprinceos` and edited via the dashboard), the public site should read from those tables via the ORM instead of the API.

This is a **data-source swap**: reproduce the four service functions' exact return shapes from the ORM so `web/views.py` and every public template stay unchanged (aside from one import line). Verified consumers: `web/views.py` imports `CINEMA_TZ, get_now_showing, get_coming_soon, get_calendar_month, get_classic_movie_night` from `web.services.leprinceos`. `web/services/showtimes.py` (`today_eastern`, `upcoming_dates`, `format_showtime_date`) is data-shape-agnostic and stays as-is.

## Decisions

- **Module:** create `web/services/cinema_data.py` (ORM-based) with the four functions + helpers, repoint the `web/views.py` import, and **delete `web/services/leprinceos.py`** ("leprinceos" is a misnomer once it no longer calls that API).
- **Caching:** **drop** the per-request cache + stale-on-failure fallback (they existed to cope with API latency/flakiness; local ORM queries are fast and always current — important now that dashboard edits must show immediately). Removes `requests` from the public request path.
- **Behavior:** **preserve the existing return shapes and quirks byte-for-byte** (e.g. Now Showing / Calendar titles use the *primary film's* title, not a double-feature "A + B"; `genre` is always `""`). Pure source swap; the public pages look and behave identically.
- `LEPRINCEOS_BASE_URL` stays in settings (still used by the `import_leprinceos` command).

## Architecture

### `web/services/cinema_data.py`

Exports `CINEMA_TZ` (so `web/views.py`'s existing `from … import CINEMA_TZ, …` becomes a one-line module-path change) and the four functions, each returning the **same dict shape** as today. Local helpers work on aware `datetime`s (not ISO strings, since `Showtime.starts_at` is already an aware datetime):

- `_format_showtime(dt)` → `dt.astimezone(CINEMA_TZ).strftime("%I:%M %p").lstrip("0")` (e.g. "6:00 PM").
- `_local_date(dt)` → `dt.astimezone(CINEMA_TZ).date()`.
- `_format_runtime(minutes)` → unchanged ("1h 40min" / "40min" / "1h" / "").

Model mapping (API field → ORM): `film_title` → `engagement.primary_film.title`; `film_poster_url` → `engagement.primary_film.poster_url`; `display_title` → `engagement.display_title`; `films[]` → `engagement.ordered_films` (`{id,title,poster}`); `is_free_for_members` → `engagement.is_free_for_members`; film `rating/runtime_minutes/synopsis/youtube_id` → `engagement.primary_film.*`. Querysets `select_related("screen")`/`prefetch_related("engagement_films__film")` to avoid N+1 on `primary_film`/`ordered_films`.

**`get_now_showing()`** — CONFIRMED engagements overlapping the next 7 days and visible:
`Engagement.objects.filter(status="CONFIRMED", start_date__lte=today+7d, end_date__gte=today).exclude(show_in_main_listings=False)`. For each, its non-cancelled showtimes grouped by local date → `{date_iso: ["6:00 PM", …]}`. Emit `{id(str), title=primary_film.title, rating, runtime, genre="", poster, showtimes, youtube_id, is_free_for_members}`. Drop movies with no showtimes.

**`get_coming_soon()`** — CONFIRMED engagements starting tomorrow+, non-CLASSIC, deduped by film-id set (double feature = distinct set):
`Engagement.objects.filter(status="CONFIRMED", start_date__gte=today+1d).exclude(kind="CLASSIC")`. Emit `{id(str), title=display_title or primary_film.title, start_date(iso), release_date="%B %-d", genre="", poster, films=[{id,title,poster}], description=primary_film.synopsis, youtube_id, is_free_for_members}`.

**`get_calendar_month(year, month)`** (month **0-based**) — non-cancelled showtimes whose local day falls in the month, grouped by day-of-month (int), deduped per day by title:
compute aware month bounds in `CINEMA_TZ` (`cal_month = month+1`; day 1 00:00:00 → last day 23:59:59), `Showtime.objects.filter(is_cancelled=False, starts_at within bounds)`. → `{day(int): [{id(str), title=primary_film.title, poster, youtube_id}]}` or `{}`.

**`get_classic_movie_night()`** — CONFIRMED CLASSIC engagements with `end_date__gte=today`, expanded into one screening per non-cancelled future showtime, enriched, sorted by date:
`Engagement.objects.filter(kind="CLASSIC", status="CONFIRMED", end_date__gte=today)`. Emit screenings `{id(str), title=display_title or primary_film.title, poster, rating, runtime, synopsis, youtube_id, date(iso), display_date="%A, %B %-d"}`, then `{"next_screening": screenings[0] or None, "upcoming": screenings[1:]}`.

All four use `timezone.localdate()`-based "today" in `CINEMA_TZ` (the site's timezone).

### `web/views.py`

Change only the import source: `from web.services.cinema_data import (CINEMA_TZ, get_now_showing, get_coming_soon, get_calendar_month, get_classic_movie_night)`. No view-body or template changes.

### Deletions

- `web/services/leprinceos.py` (retired).
- `web/tests/test_leprinceos.py` (HTTP-mock tests) → replaced by `web/tests/test_cinema_data.py` (ORM-fixture tests).

Any other test that mocks `web.services.leprinceos.*` (e.g. `test_pages.py`, `test_e2e.py`) is updated to seed `cinema` fixtures or patch `web.services.cinema_data.*` instead — verified and adjusted during implementation.

## Testing

`web/tests/test_cinema_data.py` (Django `TestCase`, seeds `cinema` models — no network):
- **now_showing:** a CONFIRMED engagement active this week with 2 non-cancelled showtimes on 2 days → one movie with `showtimes` grouped by date + correct "H:MM AM/PM" strings; a hidden (`show_in_main_listings=False`) engagement is excluded; an engagement whose window doesn't overlap the next 7 days is excluded; a movie with only cancelled showtimes is dropped; `is_free_for_members` reflects the kind.
- **coming_soon:** future CONFIRMED non-CLASSIC engagements returned; a CLASSIC future engagement excluded; two future engagements with the same film set deduped to one; `release_date`/`films[]`/`description` shapes correct.
- **calendar_month:** 0-based month maps to the right calendar month; showtimes grouped by local day-of-month; per-day title dedup; a 23:00-local showtime lands on the correct local day; empty month → `{}`.
- **classic_movie_night:** CLASSIC screenings future-only, sorted, split into `next_screening` + `upcoming`; past showtimes excluded; no classics → `{"next_screening": None, "upcoming": []}`.
- **tz correctness** for showtime formatting/date bucketing.

Page-level tests (`test_pages.py`) continue to pass against seeded data.

## Out of scope

- Any template/CSS/layout change to the public pages.
- The dashboard, the `cinema` models, or the `import_leprinceos` command.
- Removing `LEPRINCEOS_BASE_URL` or the `requests` dependency (TMDB + the import command still use them).
- Behavior changes/quirk fixes (explicitly preserved).

## Verification

- `python manage.py check` clean; `makemigrations --check` clean (no model changes).
- `web` + full suite green.
- Manual (browser): with the DB seeded (via `import_leprinceos --flush`), the home page Now Showing + Coming Soon, the calendar month view + month nav, and the Classics page render identically to the API-backed version — and reflect a dashboard edit immediately (no cache lag).
