# Dashboard Port — Screens — Design

**Date:** 2026-07-06
**Status:** Approved (design phase)
**Repo:** `api_fortkentcinema_com` (branch `feat/dashboard`)

## Context

Sub-project 2 of 5 in the leprinceos dashboard port (see `2026-07-05-dashboard-foundation-design.md` for the cross-cutting decisions and the completed Foundation shell). This sub-project replaces the stub `/dashboard/screens` route with the real, pixel-faithful **Screens** CRUD page, operating on the `cinema.Screen` model via the Django ORM. It also introduces the shared **Drawer** primitive that the Engagements sub-project will reuse.

Source: `www_leprinceos_com/src/pages/Screens.tsx` (+ `Screens.module.css`) and `src/components/Drawer.tsx` (+ `Drawer.module.css`). The React page is a react-query CRUD: a responsive list (desktop table + mobile cards) with an empty state, a slide-in Drawer holding the create/edit form, and delete-with-confirm. All interactivity is reproduced with HTMX + Alpine + Django `ModelForm`s.

## Cross-cutting decisions (inherited from Foundation)

Server-rendered Django + HTMX + Alpine; verbatim CSS ports; `is_staff` gate via `StaffRequiredMixin`; reuse the Foundation **Toast** (`window.dashboardToast`) and **Confirm** (`window.dashboardConfirm`) primitives; templates + `ModelForm`s. Only `dashboard/` files change (plus, if unavoidable, a stub-view replacement in `dashboard/views.py`/`urls.py` already owned by the dashboard app).

## Architecture

### Shared Drawer primitive

Port `Drawer.tsx`/`Drawer.module.css` into a reusable Alpine-driven slide-in panel in the `dashboard` app (used by Screens now, Engagements later):

- `drawer.css` — **verbatim** copy of `Drawer.module.css` (classnames `overlay`, `drawer`, `sm`/`md`/`lg`, `header`, `title`, `closeButton`, `content`, `footer`).
- A persistent drawer shell rendered once in the page, controlled by an Alpine `drawer` store: `open(title)`, `close()`, body-scroll lock, ESC-to-close, overlay-click-to-close (mirrors `Drawer.tsx`'s effects). Width defaults to `md`.
- The drawer's **content** region is an HTMX swap target: "New"/"Edit" buttons `hx-get` a form fragment into it and open the drawer; the footer's submit button targets the in-drawer form via `form=` attribute (as the source does).

Focus-trap is a nice-to-have; ESC + scroll-lock + focus-first-input are the behaviors we port. (Full Tab focus-trap can be added later if needed — flagged, not built, to avoid over-engineering.)

### Screen form

`ScreenForm(ModelForm)` over `cinema.Screen` with fields `name, capacity, screen_type, aspect_ratio, sound_system, supports_3d`. Widgets styled with the design-system `input`/select classes and the source's placeholders ("e.g., Screen 1, Main Auditorium"; "e.g., 150"); `supports_3d` as the `checkboxLabel` checkbox. Rendered inside the drawer via a `_screen_form.html` fragment that shows field errors inline on re-render.

### List page

`ScreenListView` renders `screens.html` (extends `base_dashboard.html`) from `Screen.objects.all()` (model ordering is by `name`). Ports **both** views verbatim from the source, driven by the same CSS:
- Desktop `tableWrapper > table`: columns Name / Capacity ("{{ n }} seats") / Type badge / Aspect Ratio / Sound / 3D badge / Actions (Edit, Delete).
- Mobile `cardList > card`: title + type badge, capacity + 3D, aspect-ratio + sound details, Edit/Delete actions.
- Empty state (🎭) with "Add First Screen".
- Human-readable labels for the enum values (Standard / IMAX / Dolby Cinema; Flat (1.85:1) / …; Standard / Dolby Digital / Dolby Atmos) — via the model's `get_FOO_display()` where it matches, or a small mapping in the template context where the source's labels differ from the model's `choices` labels.
- `screens.css` — verbatim copy of `Screens.module.css`.

### HTMX CRUD flow

- **New / Edit:** button `hx-get`s `screen_create`/`screen_edit` → returns the `_screen_form.html` fragment; Alpine opens the drawer.
- **Submit:** the form `hx-post`s to the same endpoint, targeting the drawer content (`hx-target="#drawer-content"`). On **success** → respond with the re-rendered list region as an out-of-band swap (`_screen_list.html` wrapping `#screen-list` with `hx-swap-oob="true"`) plus an `HX-Trigger` response header carrying two events: `close-drawer` (Alpine closes the drawer) and `dashboard-toast` (payload `{kind:'success', message:'Screen created'/'Screen updated'}`, consumed by a small listener that calls `window.dashboardToast`). On **validation error** → respond with the `_screen_form.html` fragment (status 200) which swaps into `#drawer-content`, showing inline field errors; the drawer stays open.
- **Delete:** the Delete button calls `window.dashboardConfirm({title:'Delete Screen', message:'Are you sure you want to delete "<name>"? This may affect existing engagements and showtimes.', confirmLabel:'Delete', variant:'danger'})`; on confirm, `hx-delete` (or `hx-post` to `screen_delete`) → remove the row/card and Toast success. Because `Screen` is `on_delete=PROTECT` from `Engagement`/`Showtime`, the view **catches `django.db.models.ProtectedError`** and returns a precise error Toast — e.g. "Can't delete "Screen 1" — it's used by 2 engagement(s) and 5 showtime(s)." — instead of a 500. The screen is not deleted.

### Views & routing

Replace the Foundation stub with real class-based views (all `StaffRequiredMixin`), namespaced under `dashboard`:
- `screens` (list) — reuse the existing name `dashboard:screens`.
- `screen_create`, `screen_edit` (pk), `screen_delete` (pk).

## Testing

Django `TestCase` (`dashboard/tests/test_screens.py`):
- List renders a row per screen + the enum labels + 3D badge; empty DB renders the empty state.
- `GET screen_create`/`screen_edit` return the form fragment (edit pre-filled from the instance).
- Valid `POST screen_create` creates a Screen and returns the refreshed list; invalid POST (blank name / capacity < 1) re-renders the form with errors and creates nothing.
- `POST screen_edit` updates fields.
- `screen_delete` on an unreferenced screen removes it; on a screen referenced by an Engagement/Showtime it is **not** deleted and the response signals the protected-error message (assert the screen still exists + the error surfaced).
- All endpoints reject anonymous (302) and non-staff (403) — one representative check.

Browser/pixel verification (side-by-side vs the React Screens page) happens after build.

## Out of scope

- Engagements, EngagementDetail, Home (later sub-projects).
- Pagination/search/sort on the list (the source lists all screens unpaginated).
- Full Tab focus-trap in the Drawer (ESC + scroll-lock + focus-first-input only).

## Verification

- `python manage.py check` clean; `dashboard` tests green; full project suite green.
- Manual: create/edit/delete a screen through the drawer; attempt to delete a screen used by an engagement and confirm the precise toast; compare pixels with the React page.
