# Dashboard Port — Engagements — Design

**Date:** 2026-07-07
**Status:** Approved (design phase)
**Repo:** `api_fortkentcinema_com` (branch `feat/dashboard`)

## Context

Sub-project 4 of the leprinceos dashboard port. Builds the pixel-faithful **Engagements** page over `cinema.Engagement` — filter tabs, a responsive list with an inline status control, and a create/edit drawer whose form embeds the FilmSearchCombo (sub-project 3) and manages the ordered film set. The per-engagement detail view (inline showtimes etc.) is sub-project 5; a "Details" link points at a stub route here.

Source: `www_leprinceos_com/src/pages/Engagements.tsx` (+ `Engagements.module.css`), `src/components/StatusDropdown.tsx` (+ `.module.css`), `src/utils/engagementKinds.ts` (KIND_LABELS).

## Cross-cutting decisions (inherited)

Server-rendered Django + HTMX + Alpine; verbatim CSS ports; `is_staff` gate; reuse Foundation Drawer/Toast/Confirm primitives; CSRF wired globally; dashboard-authored styles in `dashboard.css`. Reuse the FilmSearchCombo (`_film_search_combo.html`) and its `film-selected` event.

## Decisions (this sub-project)

- **Inline status change** re-renders the **whole engagement row** (not just the status cell).
- **Editing the film set** replaces all `EngagementFilm` rows on save (order-preserving), rather than diffing.
- The engagement create/edit form uses a **single** FilmSearchCombo instance (films are added one at a time even for double features), so the multi-combo scoping caveat from sub-project 3 does not apply.

## Architecture

### List page

`EngagementListView` renders `engagements.html` from a tab-filtered queryset. `Engagement` ordering is `start_date`.

- **Filter tabs** (`.filter-tabs` from the design system): Current / Upcoming / Draft / Ended / Cancelled. Each maps to a composite queryset (today = `timezone.localdate()`):
  - CURRENT: `status=CONFIRMED, start_date<=today, end_date>=today`
  - UPCOMING: `status=CONFIRMED, start_date>today`
  - ENDED: `end_date<today`
  - DRAFT: `status=DRAFT`; CANCELLED: `status=CANCELLED`
  - Default tab: CURRENT. The active tab is passed via `?tab=`; switching a tab HTMX-swaps the `#engagement-list` region.
- **Table + mobile cards** (verbatim `engagements.css`): Film cell (poster thumb + `display_title` + kind badge when kind≠REGULAR + "Hidden" badge when not `show_in_main_listings`), Screen (`screen.name`), Dates (`M j, Y - M j, Y`), Format (uppercased), Status (inline dropdown), Actions (Details / Edit / Delete). Per-tab empty states (🎬).
- **`film_poster_url`/`display_title`/`screen_name`**: the React API exposed these as serializer fields; here they come from the model — `engagement.display_title` (property), `engagement.screen.name`, and the primary film's poster via `engagement.primary_film.poster_url` (a small template/context helper). Kind badge label from a `KIND_LABELS` map (badge labels, e.g. SPECIAL_EVENT→"Event") ported from `engagementKinds.ts` — distinct from the form-select labels.

### Inline StatusDropdown

`_status_dropdown.html` + `StatusDropdown.module.css` (verbatim) + an Alpine `statusDropdown` component (open/close, click-outside, Escape; locked when status is ENDED or the engagement has ended by date). Choosing a status HTMX-POSTs `engagement_status`(pk) with the new status; the view updates `status` and returns the **re-rendered engagement row** (`_engagement_row.html`, targeted swap of that `<tr>`/card) + a toast. DRAFT/CONFIRMED/CANCELLED are selectable; ENDED is never manually set.

### Create/edit drawer form

`EngagementForm` (`ModelForm`, fields: `kind, event_title, screen, start_date, end_date, presentation_format, status, show_in_main_listings, notes`; status choices DRAFT/CONFIRMED/CANCELLED only) rendered in `_engagement_form.html` inside the shared drawer. Films are handled outside the ModelForm:

- **Alpine `engagementForm` component** holds `films` (array of `{id,title,poster}`) and `kind`. It listens for `film-selected` (from the embedded combo) and appends/replaces per kind (DOUBLE_FEATURE appends w/ dedupe; others replace). It renders the selected film(s): single-film kinds show the current selection; DOUBLE_FEATURE shows an ordered `<ol class="filmList">` (position badge, poster, title, Remove). Changing `kind` trims to one film when leaving double-feature and sets `show_in_main_listings` default (REGULAR→true else false). Hidden inputs emit the ordered `films` ids for submit.
- **Submit** posts the form fields + ordered `films` ids to `engagement_create`/`engagement_edit`. The view: validates the ModelForm and the film-set rule (DOUBLE_FEATURE ≥2 films, else exactly 1; screen+dates required; `end_date >= start_date` via `Engagement.clean`). On success, in a `transaction.atomic()` it saves the Engagement and **replaces** its `EngagementFilm` rows (`position` = order), returns the OOB `#engagement-list` swap + `HX-Trigger` `close-drawer` + success toast. On invalid, re-renders `_engagement_form.html` with errors (drawer stays open). Film-set errors surface as a non-field message in the form.

### Views & routing (`dashboard`, staff-gated)

- `engagements` (list, reuse existing name) — replaces the Foundation `EngagementsStubView`.
- `engagement_create`, `engagement_edit`(pk), `engagement_delete`(pk), `engagement_status`(pk).
- `engagement_detail`(pk) — **stub** (placeholder page) so the Details link resolves; sub-project 5 replaces it.

### Delete

`Engagement`→`Showtime` and →`EngagementFilm` are CASCADE, and the engagement is the parent (screen is PROTECT the other way), so delete simply cascades. Delete button uses the themed `dashboardConfirm` via the `data-dashboard-confirm` bridge → HTMX POST → refreshed list + toast.

## Testing

- Filter-tab querysets (each tab returns the right engagements given fixture dates/status; default CURRENT).
- List renders row/card fields, kind badge (only when ≠REGULAR), Hidden badge, per-tab empty state.
- Inline status: POST updates status + returns the re-rendered row; ENDED (by status or past end_date) is locked (the dropdown button is disabled / no options rendered).
- Create: single-film kind creates 1 EngagementFilm (position 1); DOUBLE_FEATURE with 2 films creates 2 in order; success fires OOB list + close + toast.
- Validation: DOUBLE_FEATURE with <2 films, missing screen/dates, and end_date<start_date each re-render the form with an error and create nothing.
- Edit: replaces the film set (old EngagementFilm rows gone, new ones in order) and updates fields.
- Delete: removes the engagement (and cascades its showtimes/film-links); confirm required; refreshed list.
- Staff gate on all endpoints.

Browser/pixel verification (list, tabs, status dropdown, the create drawer with the film picker + double-feature ordering) after build.

## Out of scope

- EngagementDetail page (sub-project 5) — only a stub route here.
- Home (sub-project 6).
- The Alt+N shortcut already navigates to `/dashboard/engagements` (Foundation); wiring it to auto-open the create drawer is a nicety deferred to when it matters (not required for parity of this page).

## Verification

- `python manage.py check` clean; `makemigrations --check` clean (no model changes).
- `dashboard` + `cinema` suites green; full project suite green.
- Manual: create a single-film and a double-feature engagement through the drawer (film picker + ordering), edit one (film set replaced), flip status inline, filter through the tabs, delete one; compare pixels with the React Engagements page.
