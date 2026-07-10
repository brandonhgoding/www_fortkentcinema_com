# Dashboard Port — Home — Design

**Date:** 2026-07-09
**Status:** Approved (design phase)
**Repo:** `api_fortkentcinema_com` (branch `feat/dashboard`)

## Context

Sub-project 6 (final) of the leprinceos dashboard port. Builds the `/dashboard/` overview — header, smart alerts, three summary cards, and today's showtimes — replacing the Foundation placeholder Home. After this, the entire staff dashboard is ported to server-rendered Django.

Source: `www_leprinceos_com/src/pages/Home.tsx` (+ `Home.module.css`), `src/hooks/useSmartAlerts.ts`; alerts render through the already-ported `AlertBanner` markup/CSS (Foundation).

## Cross-cutting decisions (inherited)

Server-rendered Django + HTMX + Alpine; verbatim CSS port; `is_staff` gate; reuse Foundation chrome + `alertbanner.css`; all counts/data computed server-side from the `cinema` models with `timezone.localdate()` / aware ranges in `America/New_York` (`USE_TZ=True`).

## Decisions (this sub-project)

- **Summary cards** are ported WITHOUT the React `SummaryCard` trend/previousValue/loading branches — Home never passes those props (dead UI). YAGNI: port only the label + value + optional link.
- **Smart alerts** are static, server-rendered banners (page-load), **dismissible client-side only** via Alpine `x-show` (no persistence — reappear on reload, matching the source). They use the `AlertBanner` classnames, NOT the Alpine toast store (that store is for transient action feedback).

## Architecture

### HomeView

`HomeView` (replaces the Foundation placeholder `HomeView`) with `StaffRequiredMixin`, rendering `dashboard/home.html`. Computes everything server-side:

- `today = timezone.localdate()`; `tomorrow = today + 1 day`.
- **Today's local-day UTC range:** `start = make_aware(datetime.combine(today, time.min))`, `end = make_aware(datetime.combine(tomorrow, time.min))`; today's showtimes = `Showtime.objects.filter(starts_at__gte=start, starts_at__lt=end)` (aware, so this is the correct local day). Same pattern for tomorrow's range (used only for the alert count).
- Context:
  - `active_engagements_count = Engagement.objects.filter(status="CONFIRMED").count()`
  - `screens_count = Screen.objects.count()`
  - `today_showtimes = <today range qs>.select_related("screen").prefetch_related("engagement__engagement_films__film").order_by("starts_at")`
  - `today_showtimes_count = len(today_showtimes)` (or `.count()`)
  - `alerts = build_smart_alerts(...)` (below)
  - `display_name = request.user.get_short_name() or request.user.get_username()` (source used `first_name || username`).

### Summary cards

`_summary_card.html` (or inline in home.html) — porting `SummaryCard`'s used subset: a card with `cardLabel`, `cardValue`, and an optional `cardLink` (`{text} →`). Three cards:
1. Active Engagements → value + "View all" link to `dashboard:engagements`.
2. Today's Showtimes → value only.
3. Screens → value + "Manage" link to `dashboard:screens`.

`summaryGrid` layout; verbatim `home.css`.

### Today's showtimes

Desktop table (Time / Film / Screen / Format / Status) + mobile cards (`showtimeCard*`) + the 🎬 `empty-state` (with a "View Engagements" CTA), sorted by `starts_at`. Fields from the model:
- Time: `{{ st.starts_at|date:"g:i A" }}` (rendered in the active tz).
- Film: `st.engagement.display_title` (source used a `film_title` serializer field; `display_title` is the model equivalent).
- Screen: `st.screen.name`.
- Format: `st.engagement.presentation_format|upper` (source used `presentation_format_display`, i.e. "2D"/"3D").
- Status: Cancelled/Active badge (`statusCancelled`/`statusActive`).

### Smart alerts

`cinema`-agnostic helper in `dashboard/` — `build_smart_alerts(engagements, tomorrow_showtimes_count, today) -> list[dict]` (each `{"id", "type", "message"}`), a faithful port of `useSmartAlerts`:
1. **No showtimes tomorrow:** if `tomorrow_showtimes_count == 0` AND `engagements` is non-empty → `{"id":"no-showtimes-tomorrow","type":"warning","message":"No showtimes scheduled for tomorrow"}`.
2. **Ending soon:** for each CONFIRMED engagement with `today <= end_date <= today+2days`, `days_left = (end_date - today).days` → `{"id":f"ending-soon-{e.id}","type":"info","message":f"{e.display_title} ends in {days_left} day{'s' if days_left != 1 else ''}"}`. (Source used `film_title`; use `display_title`. Source computed `daysLeft` via ceil of a ms diff; with date-only subtraction `.days` is the exact integer equivalent.)
3. **Drafts:** `draft_count = engagements.filter(status="DRAFT").count()`; if > 0 → `{"id":"draft-engagements","type":"info","message":f"You have {draft_count} draft engagement{'s' if draft_count != 1 else ''} waiting to be confirmed"}`.

`engagements` passed to the helper = `Engagement.objects.all()` (source fetched all engagements for alerts).

Rendered via `_alerts.html` reproducing the `AlertBanner` structure (`alertContainer`, `alert alert{Type}`, `alertIcon`, `alertMessage`, `dismissButton`), each wrapped so an Alpine `x-data="{ shown: true }"` + the dismiss button's `@click="shown=false"` + `x-show="shown"` hides it (no persistence). Icons per type from the same map as the toast primitive (⚠ ℹ ✓ ✕).

### Routing

No new routes — `dashboard:home` already exists (Foundation); its view is swapped from the placeholder to the real `HomeView`.

## Testing

Django `TestCase`:
- Counts: Active Engagements (only CONFIRMED), Screens, Today's Showtimes (tz-correct — a showtime at 23:00 local today counts today, not tomorrow).
- Today's showtimes list: sorted by time, film/screen/format/status rendered, Cancelled badge, 🎬 empty state when none.
- Smart alerts: no-showtimes-tomorrow fires only when engagements exist and tomorrow is empty; ending-soon at the boundaries (end today, end +2, excluded at +3 and when DRAFT); draft count + singular/plural wording; a clean state yields no alerts.
- `display_name` uses first name when set, else username.
- Staff gate (anon → 302, non-staff → 403).

Browser/pixel verification (cards, alerts, today's showtimes table/cards, empty state) after build — folded into the full-dashboard browser pass.

## Out of scope

- Trend/previous-week indicators (never wired into Home in the source).
- Alt+N auto-open create drawer (Foundation already navigates to `/dashboard/engagements`).
- Any showtime/engagement mutation from Home (read-only overview).

## Verification

- `python manage.py check` clean; `makemigrations --check` clean (no model changes).
- `dashboard` suite green; full project suite green.
- Manual: seed a CONFIRMED engagement with showtimes today + a draft; confirm the three counts, today's list, and the three alert types; dismiss an alert (hides until reload). Compare pixels with the React Home.
