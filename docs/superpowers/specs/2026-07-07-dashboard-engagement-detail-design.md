# Dashboard Port — EngagementDetail — Design

**Date:** 2026-07-07
**Status:** Approved (design phase)
**Repo:** `api_fortkentcinema_com` (branch `feat/dashboard`)

## Context

Sub-project 5 of the leprinceos dashboard port. Builds the per-engagement detail page at `/dashboard/engagements/<id>` — a read-only info panel plus full **showtimes** management (list, single create/edit/delete, and bulk add across a date range). Replaces the stub route added in sub-project 4. Home (sub-project 6) is the last piece.

Source: `www_leprinceos_com/src/pages/EngagementDetail.tsx` (+ `.module.css`), `src/api/showtimes.ts`; backend `api_leprinceos_com/showtimes/services/overlap_service.py` and `api/v1/views/showtimes.py` (bulk-create).

## Cross-cutting decisions (inherited)

Server-rendered Django + HTMX + Alpine; verbatim CSS ports; `is_staff` gate; reuse Drawer/Toast/Confirm primitives; CSRF global. HTMX list-region GETs return only the partial on `HX-Request` (the rule established in sub-project 4). `USE_TZ=True`, `TIME_ZONE="America/New_York"`.

## Decisions (this sub-project)

- **Conflict handling: full overlap port.** Port `overlap_service.py` into `cinema/` (verbatim + 2-line import rewrite). Both single and bulk create validate runtime-aware overlaps (start + film runtime, or a 150-min default, + 30-min buffer). Bulk is **all-or-nothing** — any overlap (against existing or intra-batch) rejects the whole batch with deduplicated conflict messages.
- Showtimes inherit the engagement's screen (`Showtime.save()` defaults `screen_id` from the engagement), so no screen field on the forms.
- Date+time are combined into an aware `starts_at` in `America/New_York`.

## Architecture

### Overlap service (`cinema/showtimes_overlap.py`)

Verbatim copy of `showtimes/services/overlap_service.py` with imports rewritten `from cinemas.models import Screen` / `from showtimes.models import Showtime` → `from cinema.models import Screen, Showtime`. Exposes `OverlapConflict`, `get_effective_end`, `check_overlap_against_existing(screen, starts_at, runtime_minutes, film_title, exclude_showtime_id=None)`, `check_intra_batch_overlaps(proposed)`, `format_overlap_error(conflict)`, and `_ProposedShowtime`. Its 319-line source test suite is ported too (import-rewritten) to lock the behavior.

### Read-only detail page

`EngagementDetailView` (replaces the sub-project-4 `EngagementDetailStubView`) renders `engagement_detail.html` from `get_object_or_404(Engagement, pk)`; 404 → the "not found" template block. `EngagementDetail.module.css` ported verbatim. Content:

- Header: back link to `dashboard:engagements`, `engagement.display_title`, subtitle.
- **Film Details** card: first film's poster; ordered film list (`engagement.engagement_films` by position) with order number (when >1), thumbnail (skipped for the first — its poster is the hero), title, runtime.
- **Engagement Details** card: status badge (`statusConfirmed/Draft/Cancelled/Ended` classes keyed off `engagement.status`), kind (`KIND_LABELS`), event title (only when set and ≠ display_title), "Hidden from public listings" note, screen name, format (upper), start/end dates, notes.

### Showtimes list

`_showtime_list.html` (`#showtime-list` region) rendered inside the page and returned on any showtime mutation (OOB refresh, same pattern as engagements). `Showtime.objects.filter(engagement=…).order_by("starts_at")` (the model already orders by `starts_at`). Desktop table (Date & Time via `{{ st.starts_at|date:"..." }}` localized to the active tz, Screen, Captions badge or —, Status Active/Cancelled, Actions Edit/Delete; `cancelledRow` class) + mobile cards + empty state. The mutation views return the refreshed `#showtime-list` OOB + `HX-Trigger` (close-drawer where relevant + toast).

### Single create/edit (drawer)

A hand-built form fragment `_showtime_form.html` (not a plain ModelForm, since the UI splits `starts_at` into date + time): fields **Date** (`type=date`, `min=engagement.start_date`, `max=engagement.end_date`), **Time** (`type=time`), **Captions** (None/CC/OC), and **Cancelled** checkbox (edit only). The view:
- `starts_at = make_aware(datetime.combine(date, time), ZoneInfo("America/New_York"))`.
- Runs `check_overlap_against_existing(screen=engagement.screen, starts_at, runtime=engagement.total_runtime_minutes, film_title=engagement.display_title, exclude_showtime_id=<self on edit>)`; overlaps (unless the showtime is being cancelled) → re-render the form with the conflict messages. Cancelling (`is_cancelled=True`) skips the overlap check, mirroring the source.
- On success: create/update the Showtime (screen defaults from the engagement via `save()`), return OOB `#showtime-list` + close-drawer + toast.
- Validation: date and time required; date within engagement range is a soft `min/max` on the input (the model's `clean()` is a no-op — outside-range is a soft warning, not blocked), matching the source.

### Bulk add (drawer)

`_showtime_bulk_form.html` + an Alpine `bulkShowtimeForm` component holding a `times` array (start with one; add/remove slots, always keep ≥1). Fields: Start/End Date (within engagement range), the dynamic time slots (`type=time`), Captions. The view:
- Builds a `Showtime` per day in `[start_date, end_date]` × each non-empty time, `starts_at` aware in the cinema tz, `screen=engagement.screen`, `captions`.
- In a `transaction.atomic()` with `Screen.objects.select_for_update()`: run `check_overlap_against_existing` for each proposed against the DB and `check_intra_batch_overlaps` across the batch; if any conflicts → 200 response re-rendering the bulk form with the deduplicated error list, create nothing. Else `Showtime.objects.bulk_create(...)`, return OOB `#showtime-list` + close-drawer + toast ("Created N showtimes").
- Validation: start/end date and ≥1 non-empty time required.

### Delete

Delete button → themed `dashboardConfirm` → HTMX POST `showtime_delete` → delete + OOB `#showtime-list` refresh + toast.

### Views & routing (`dashboard`, staff-gated, under `/dashboard/engagements/<eng_pk>/showtimes/`)

- `engagement_detail`(pk) — real view (replaces stub).
- `showtime_create`(eng_pk) GET form / POST create; `showtime_edit`(pk) GET/POST; `showtime_delete`(pk) POST; `showtime_bulk`(eng_pk) GET form / POST bulk.

## Testing

- **Overlap service:** the ported 319-line test suite (import-rewritten) passes against `cinema` models.
- Detail page: renders engagement fields, film list (order + runtime), status badge, notes, hidden note; 404 for a missing engagement; staff gate.
- Showtimes list: renders rows/cards, captions badge, cancelled styling, sorted, empty state.
- Single create: combines date+time into the correct aware `starts_at`; overlap against an existing showtime re-renders the form with a conflict message and creates nothing; a non-overlapping time creates it; edit updates; cancelling skips the overlap check.
- Bulk: a 3-day range × 2 times creates 6 showtimes; an overlap (existing or intra-batch) rejects the whole batch with errors and creates nothing; the Alpine times array add/remove works (render assertions).
- Delete removes a showtime + refreshes.

Browser/pixel verification (detail layout, showtimes table, both drawers incl. the dynamic time slots) after build.

## Out of scope

- Home (sub-project 6).
- Editing engagement fields from this page (done via the Engagements list Edit drawer, sub-project 4); this page is read-only for engagement info + full CRUD for its showtimes.

## Verification

- `python manage.py check` clean; `makemigrations --check` clean (no model changes).
- `cinema` + `dashboard` suites green; full project suite green.
- Manual: open an engagement's detail; add a showtime; try an overlapping time (conflict message); bulk-add across the run at two times (6 created); try a bulk overlap (rejected); cancel a showtime; delete one; compare pixels with the React page.
