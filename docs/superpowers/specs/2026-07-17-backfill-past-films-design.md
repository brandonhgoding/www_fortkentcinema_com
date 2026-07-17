# Backfill Past Films — Design

**Date:** 2026-07-17
**Status:** Approved, ready for plan

## Problem

We have ~2 years of Square sales data listing every film that has played at Fort
Kent Cinema (title, type, run start/end date). The public calendar
(`get_calendar_month`) is driven by `Showtime` rows, so past films that predate
our native `cinema` tables simply don't appear. We want a one-shot, re-runnable
management command that seeds `Film` / `Engagement` / `Showtime` records for these
past runs so they show up on the calendar, enriched with TMDB metadata where
available.

## Scope

A single Django management command:
`cinema/management/commands/backfill_past_films.py`, modeled on the existing
`link_film_reviews` command.

The 90-film dataset (from `fort_kent_cinema_films.json`) is **embedded as a Python
literal** in the command module — no external file, so it can be run directly on
prod (`python manage.py backfill_past_films`) with nothing to upload.

We also capture each run's `ticketsSold` count into a new
`Engagement.admissions` field (populated during the backfill) so total
admissions per film are available later. **Admin-only for now** — surfaced in
the Django admin, not on any public page; whether to display it publicly is a
separate decision once the real numbers are visible.

Out of scope: importing `daysWithSales`, picking exact real screens/times (we
don't have that data), any public display of admissions, backfilling anything
other than calendar-visibility showtimes.

## Invocation

```
python manage.py backfill_past_films [--dry-run] [--sleep 1.0]
```

- `--dry-run` — perform TMDB lookups (so matches can be eyeballed) but write
  nothing to the database.
- `--sleep` — seconds to pause between TMDB lookups (default `1.0`) to stay under
  TMDB rate limits.

## Data model recap

- `Film` — `import_film_from_tmdb(tmdb_id)` in `cinema/services.py` already
  reuses a film by `tmdb_id` or creates it with poster/backdrop/overview/runtime.
- `Engagement` — FK `screen` (PROTECT), `start_date`/`end_date`, `kind`
  (REGULAR / SPECIAL_EVENT / CLASSIC / DOUBLE_FEATURE), `status`,
  `show_in_main_listings`, `notes`. Helper
  `Engagement.default_visibility_for(kind)` returns `True` only for REGULAR.
- `EngagementFilm` — through table, unique `(engagement, position)`.
- `Showtime` — FK `engagement`, FK `screen`, `starts_at` (DateTimeField, UTC).
  **`UniqueConstraint(screen, starts_at)`** — the key constraint the placement
  logic must respect.
- Screens on prod: `The Century` and `The Savoy` (both capacity 1).

## Per-film algorithm

Films are processed in dataset order. For each entry `{title, type, startDate,
endDate, notes}`:

### 1. Skip check (cheap, no API call)

Normalize the title (`slugify`) and look for an existing `Film` whose slug or
normalized title matches **and that already has engagements**
(`film.engagements.exists()`). If found → **SKIP** (this fast-paths the ~46
films already imported from leprinceos) without spending a TMDB call.

### 2. Resolve the film via TMDB

Otherwise call `TMDBService.search_films(title)` (then `sleep(--sleep)`).

- If results exist, take the top result's `tmdb_id` and call
  `import_film_from_tmdb(tmdb_id)` — this reuses an existing film with that
  `tmdb_id` or creates a new one with full metadata. Log the matched TMDB title +
  release year so mismatches are visible in the output.
- Re-check `film.engagements.exists()` → **SKIP** if it already has engagements.

### 3. No TMDB match → title-only film

If TMDB returns nothing, create `Film(title=title)` (slug auto-generated, no
metadata) so the run still lands on the calendar. Record it in a **title-only
list** printed in the summary for manual cleanup in admin. Entries like
`Quintuplets (Nov 4)` and `Classic Movie (various)` are expected here.

### 4. Create the engagement

- `start_date` / `end_date` from the entry.
- `kind`:
  - `type == "Film"` → `REGULAR`.
  - `type == "Special screening"` → `SPECIAL_EVENT` if `"event"` appears in the
    entry's notes (case-insensitive), else `CLASSIC`.
- `status = CONFIRMED` (these runs really happened; past dates keep them out of
  Now-Showing and Coming-Soon, which both filter on future/current dates).
- `show_in_main_listings = Engagement.default_visibility_for(kind)` — classics
  and events stay out of the main film listings.
- `notes` = the JSON note (if any) plus a `"Backfilled from Square sales data"`
  marker so these rows are auditable/removable later.
- `screen` = the engagement's default/primary screen (see placement). Set to the
  screen preferred for this engagement (rotates per-engagement to balance load).
- One `EngagementFilm(engagement, film, position=1)`.

### 5. Create conflict-free showtimes

Target **3:00pm America/New_York** on every calendar date from `start_date`
through `end_date` inclusive.

To respect `UniqueConstraint(screen, starts_at)` across the 112 overlapping
film-pairs (and any showtimes already in the DB):

- At command start, pre-load every existing `(screen_id, starts_at)` pair into an
  in-memory `set` (one query).
- For each date, find the first free slot by iterating candidate screens
  `[preferred, other]` × candidate times `[15:00, 16:00, 17:00, …]`, building the
  aware datetime for each and checking membership in the set. Take the first free
  `(screen, datetime)`, create the `Showtime`, and add it to the set.
- The preferred screen alternates per engagement (e.g. by engagement index) so
  concurrent runs spread across The Century and The Savoy rather than piling onto
  one.
- `IntegrityError` on save is caught as a backstop (advance to the next candidate
  slot) so the command can never crash on a collision.

The engagement's own `screen` FK is set to whichever screen its first showtime
lands on.

## Idempotency

Re-running is safe: once a film has any engagement it is skipped in step 1/2.
Title-only films created on a first run match in step 1 on the second run (they
now have an engagement) and are skipped. No duplicate engagements or showtimes are
created. `--dry-run` can be used first to preview all TMDB matches and skips.

## Output

Per film, one line: `CREATED`, `SKIPPED (already has engagements)`, or
`TITLE-ONLY (no TMDB match)`, with the TMDB match shown for created films. A final
summary prints counts of each outcome, total showtimes created, and the full list
of title-only films to fix by hand in admin.

## Testing

Unit tests in `cinema/tests/` (mock `TMDBService` — no live API):

1. **Skip** — a film that already has an engagement is skipped and no showtimes
   are added.
2. **Create with TMDB** — a fresh film is created from a mocked TMDB result, with
   an engagement spanning the dates and one 3pm showtime per date.
3. **Title-only** — mocked empty TMDB result creates a title-only film + engagement
   and reports it.
4. **Conflict placement** — two overlapping runs never violate
   `unique(screen, starts_at)`; the second lands on the other screen (or a later
   hour when both screens are taken).
5. **Kind mapping** — `"Film"` → REGULAR/visible; `"Special screening"` →
   CLASSIC or SPECIAL_EVENT and `show_in_main_listings=False`.
6. **Dry-run** — writes nothing to the database.
```
