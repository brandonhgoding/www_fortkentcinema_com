# leprinceos → cinema Data Import — Design

**Date:** 2026-07-09
**Status:** Approved (design phase)
**Repo:** `api_fortkentcinema_com` (branch: new `feat/leprinceos-import`)

## Context

The dashboard now operates on the native `cinema` models (`Screen`, `Film`, `Engagement`, `EngagementFilm`, `Showtime`), but those tables are empty (aside from throwaway rows seeded during the browser check). The real cinema data lives in the leprinceos SaaS and is exposed through its public read API (`https://www.leprinceos.com/api/v1`, already consumed by `web/services/leprinceos.py`). This project builds a re-runnable management command that pulls that data and rewrites the `cinema` tables to match it — the actual data migration from leprinceos into the native tables.

The `/films/`, `/engagements/`, `/showtimes/` endpoints are public and paginated (DRF). `/screens/` is auth-gated, so screens are reconstructed from the FK references (`screen` id + `screen_name`) embedded in engagements and showtimes. Verified live: 66 films, 46 engagements (with an ordered `films` array), 397 showtimes, 2 screens ("The Century" id 1, "The Savoy" id 2 — Fort Kent Cinema's own auditorium names).

## Decisions

- **Screen capacity:** the API never exposes capacity/specs. Import screens with a **placeholder `capacity=1`** and model-default tech specs; staff correct them later in the dashboard Screens page.
- **Import mode:** full **wipe + fresh import**. Re-running always reproduces the exact current API state. The wipe requires an explicit **`--flush`** flag (guard against accidental production data loss).
- **Target:** a reusable management command that runs anywhere — local dev now, production at deploy time (DB chosen by environment).

## Architecture

### `cinema/leprinceos_import.py` (service)

Testable, framework-thin logic (no `requests` calls hard-wired to the network in tests):

- `fetch_all(base_url, path, *, session=None) -> list[dict]` — GET `base_url + path`, follow DRF `next` pagination until exhausted, unwrap `results`, `raise_for_status`, reasonable timeout. Returns the full list of records.
- `import_all(base_url, *, flush, capacity_default=1) -> dict[str, int]` — orchestrates the import inside a single `transaction.atomic()`; returns counts `{"screens", "films", "engagements", "engagement_films", "showtimes"}`. Raises if `flush` is False (the command enforces the flag).

Import steps (all in one transaction — all-or-nothing):
1. **Flush** child-first: `Showtime`, `EngagementFilm`, `Engagement`, `Film`, `Screen`.
2. **Screens** — collect distinct `(screen id, screen_name)` from the union of engagements' `screen`/`screen_name` and showtimes' `screen`/`screen_name`. Create one `Screen` per distinct id with `name=screen_name`, `capacity=capacity_default`, model defaults for `screen_type`/`aspect_ratio`/`sound_system`/`supports_3d`. Build `screen_id → Screen` map.
3. **Films** — one `Film` per `/films/` record, copying `title, runtime_minutes, rating, synopsis, poster_url, backdrop_url, overview, tmdb_id, imdb_id, youtube_id`. `Film.save()` already coerces empty external ids to `None`. Build `film_id → Film` map.
4. **Engagements** — one `Engagement` per `/engagements/` record: `screen` via the map, plus `start_date, end_date, kind, event_title, presentation_format, status, show_in_main_listings, notes`. Build `eng_id → Engagement` map. Then, from the record's `films` array (ordered), create `EngagementFilm(engagement, film=film_map[f["id"]], position=index+1)`. (`created_at` is `auto_now_add`; the original timestamp cannot be restored and becomes import time — accepted.)
5. **Showtimes** — one `Showtime` per `/showtimes/` record: `engagement` via map, `screen` via map, `starts_at` parsed from the ISO string to an aware datetime (`datetime.fromisoformat`), `is_cancelled`, `captions`.

Defensive: if a showtime references an engagement id or screen id absent from the maps, or an engagement's film id is absent from the film map, skip that item and record a warning in the returned/logged summary rather than crashing (should not occur with consistent API data).

### `cinema/management/commands/import_leprinceos.py` (command)

Thin wrapper:
- Args: `--flush` (required to proceed; without it, exit with an explanatory error and change nothing), `--base-url` (default `settings.LEPRINCEOS_BASE_URL`), `--capacity` (default 1).
- Calls `import_all(...)`, prints the counts, and (on missing `--flush`) prints how to run it.

## Testing

Django `TestCase` (`cinema/tests/test_leprinceos_import.py`) — never hits the network:
- Mock `fetch_all` (or the underlying `requests`/session) to return canned films/engagements/showtimes payloads mirroring the real API shapes (including a double-feature engagement with a 2-element `films` array, a cancelled showtime, an engagement referencing a screen only otherwise seen in showtimes).
- Assert: correct row counts per table; `screen_id → Screen` reconstruction from the union of engagement + showtime references; `Film` field copy incl. empty-id → None; `Engagement` fields; `EngagementFilm` **position order matches the array order** (double feature → positions 1,2); `Showtime.starts_at` is tz-aware and equals the source instant; screen/engagement FKs resolve through the maps.
- `--flush` clears pre-existing rows before importing; `import_all(flush=False)` raises (no writes).
- A failure mid-import (e.g. a bad record) rolls back — no partial rows.
- `call_command("import_leprinceos")` without `--flush` writes nothing and errors clearly.

A manual live smoke run against dev (`--flush` against the real API) is done once by hand to confirm the real payloads import cleanly; not part of the automated suite.

## Out of scope

- Screen tech specs/capacity (not exposed by the API).
- Preserving original PKs or `created_at`.
- Incremental/delta sync (full-replace only).
- Any change to the dashboard or the public `web` site.

## Verification

- `python manage.py check` clean; `makemigrations --check` clean (no model changes).
- `cinema` suite green; full project suite green.
- Manual: `python manage.py import_leprinceos --flush` against dev → prints counts (≈2 screens, 66 films, 46 engagements, ≥47 engagement-films, 397 showtimes); dashboard then shows the real engagements/showtimes; re-running reproduces the same state.
