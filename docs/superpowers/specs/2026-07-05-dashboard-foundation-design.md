# Dashboard Port — Foundation — Design

**Date:** 2026-07-05
**Status:** Approved (design phase)
**Repo:** `api_fortkentcinema_com` (branch `feat/dashboard`)

## Context

Port the leprinceos staff **dashboard** (React 19 + TS SPA at `www_leprinceos_com`, served under `/dashboard`) into server-rendered Django in `api_fortkentcinema_com`, pixel-perfect and functionally complete, using Django template views + `ModelForm`s instead of React. The dashboard manages the **`cinema`** models already ported into this project (`Film`, `Screen`, `Engagement`, `EngagementFilm`, `Showtime`) via the ORM — NOT the leprinceos HTTP API.

The full dashboard is decomposed into **5 sequential sub-projects**, each its own spec → plan → build on the shared `feat/dashboard` branch:

1. **Foundation** (this spec) — design system, app chrome, auth/mount, shared primitives.
2. **Screens** — simplest CRUD page.
3. **Engagements** — list + filter tabs + create drawer + StatusDropdown + FilmSearch.
4. **EngagementDetail** — engagement editing + inline showtimes.
5. **Home** — dashboard overview + smart alerts.

This spec covers **Foundation only**: the `/dashboard` shell that later pages drop into, with pixel-identical chrome and a placeholder Home. No cinema CRUD yet.

## Cross-cutting decisions (apply to all 5 sub-projects)

- **Stack:** server-rendered Django templates + `ModelForm`s; **HTMX** for fragment swaps (list rows, drawer contents, inline validation); **Alpine** for local UI state (drawer open, dropdown, toast, sidebar). Both libs are already vendored at `static/js/{htmx.min.js,alpine.min.js}`.
- **Brand label:** keep **"LeprinceOS"** verbatim (sidebar brand + mobile header).
- **Fonts:** self-host Plus Jakarta Sans, Playfair Display, Cormorant Garamond (woff2 vendored into dashboard static; no runtime CDN).
- **Auth:** Django `LoginRequiredMixin` on every dashboard view; `is_staff` is the gate (no separate manager role). `LOGIN_URL` → themed `/login`; logout at `/logout/`.
- **Drop** the "API Docs" sidebar nav item (no fortkentcinema equivalent).
- **Mount:** all dashboard routes under `/dashboard/`.

## Foundation architecture

### New Django app: `dashboard`

```
dashboard/
  apps.py                         # DashboardConfig
  urls.py                         # /dashboard/ routes (namespaced 'dashboard')
  views.py                        # HomeView + stub ScreensView/EngagementsView (LoginRequiredMixin)
  forms.py                        # (empty in Foundation; cinema ModelForms land in later sub-projects)
  templates/dashboard/
    base_dashboard.html           # <head> (fonts, CSS, JS), layout shell, {% block content %}
    _sidebar.html                 # sidebar partial (brand, nav, user/logout)
    _mobile_header.html           # hamburger + brand
    _toast.html                   # Alpine toast/AlertBanner primitive (reusable include)
    _confirm.html                 # Alpine confirm-dialog primitive (reusable include)
    home.html                     # placeholder Home page content
    login.html                    # themed login (extends a minimal auth base)
  templatetags/
    dashboard_nav.py              # {% nav_active %} helper for sidebar active state
  static/dashboard/
    css/design-system.css         # verbatim port of leprinceos src/index.css
    css/layout.css                # port of Layout.module.css
    css/sidebar.css               # port of Sidebar.module.css
    css/login.css                 # themed login styles
    fonts/                        # self-hosted woff2 + @font-face (fonts.css)
    js/dashboard.js               # Alpine components (sidebar, fullscreen, toast, confirm) + Alt+N shortcut
  tests/
    __init__.py
    test_auth.py                  # login-required + is_staff gating
    test_chrome.py                # sidebar renders, active nav, all nav URLs resolve, brand text
```

### Design system CSS — verbatim port

`leprinceos/src/index.css` (~640 lines) → `dashboard/static/dashboard/css/design-system.css`, unchanged except:
- `--font-sans/serif/display` continue to reference the three families; served via self-hosted `@font-face` in `fonts/fonts.css` (imported before design-system.css).
- No other edits: keep all tokens, `@keyframes`, grain texture, reset, and the global component classes (`.page-header`, `.filter-tabs`, `.status-badge`, `.data-table-container`, `.table`, `.btn*`, `.empty-state`, `.card`, container/grid/flex/text utilities, scrollbar/selection). These classes are consumed by every later page, so exact fidelity here is what makes the whole port pixel-perfect.

The `#root` rule maps to the dashboard layout root element; `body` styles apply globally within the dashboard base template only (the public `web` site keeps its own base — the dashboard base does not extend it).

### Chrome (Layout + Sidebar) — Alpine, no React

`base_dashboard.html` reproduces `Layout.tsx`'s structure:
- Mobile header (`_mobile_header.html`): hamburger button toggles `sidebarOpen` (Alpine); brand link "LeprinceOS".
- Sidebar (`_sidebar.html`): brand, nav (Home, Engagements, Screens — **no API Docs**), user section (username + Log Out → `/logout/`). Active link via `{% nav_active %}` comparing the current URL name. Mobile slide-in + overlay driven by Alpine `sidebarOpen`; overlay click closes.
- Main container with toast region (`_toast.html`) and `{% block content %}`.
- Fullscreen toggle + `fullscreenchange` sync (Alpine `x-data` on layout root; uses the Fullscreen API).
- Keyboard hint chip ("Alt+N New Engagement") and the Alt+N handler in `dashboard.js` (navigates to engagements + opens create drawer — the drawer-open event is a no-op until the Engagements sub-project wires it; Foundation just navigates).

`isFullscreen` hides mobile header, sidebar, and the keyboard hint exactly as the source does.

### Shared primitives (for later sub-projects)

- `_toast.html` + Alpine `toast` store: `AlertBanner`-styled transient messages, dismissible, mirrors `ToastContext`. Exposed via a JS helper `window.dashboardToast(kind, message)`.
- `_confirm.html` + Alpine `confirm` store: `ConfirmDialog`-styled modal returning a promise, mirrors `ConfirmContext`. Exposed via `window.dashboardConfirm({title, message})`.

Foundation builds these primitives and smoke-tests them with a trivial trigger; later pages consume them for delete confirmations and success toasts.

### Auth

- `LoginRequiredMixin` + a small `StaffRequiredMixin` (checks `request.user.is_staff`, else 403) on all dashboard CBVs.
- `LOGIN_URL = "/login"`, `LOGIN_REDIRECT_URL = "/dashboard/"`.
- Themed login view (`django.contrib.auth.views.LoginView` with `template_name="dashboard/login.html"`, styled via `login.css`) and `LogoutView` at `/logout/`.
- Wire these auth URLs at project level (`fortkentcinema/urls.py`) only if not already present; verify no collision with existing routes.

### Routing

`fortkentcinema/urls.py` includes `dashboard.urls` under `dashboard/`. Named routes: `dashboard:home` (`/dashboard/`), `dashboard:screens` (`/dashboard/screens`), `dashboard:engagements` (`/dashboard/engagements`). Screens/Engagements are **stub `TemplateView`s** in Foundation (empty-state placeholder) so Sidebar links resolve; real pages replace them in later sub-projects.

## Testing

Django `TestCase` (`dashboard/tests/`):
- **Auth:** anonymous GET `/dashboard/` → 302 to `/login?next=/dashboard/`; authenticated non-staff → 403; staff → 200.
- **Chrome:** staff GET renders sidebar with brand "LeprinceOS", the three nav items (and NOT "API Docs"); the active nav item carries the active class for the current route; `reverse()` resolves `dashboard:home/screens/engagements`; logout link points to `/logout/`.
- **Static wiring:** `design-system.css` and `fonts.css` are referenced in the rendered `<head>`.

A browser pass (later, once a real page exists) verifies pixel fidelity against the running React dashboard.

## Out of scope (Foundation)

- Any cinema-model CRUD, forms, tables, drawers with real data (sub-projects 2–5).
- FilmSearch combobox, StatusDropdown, smart alerts (later sub-projects).
- The unrouted `Showtimes.tsx` (dead in source; showtimes live in EngagementDetail).
- Data import; the public `web` site and `web/services/leprinceos.py` (untouched).

## Verification

- `python manage.py check` clean; `dashboard` tests green.
- Manual: `runserver`, log in as staff, visit `/dashboard/` — chrome renders, sidebar nav highlights, mobile hamburger + overlay work, fullscreen toggle works, a test toast + confirm fire. Compare side-by-side with the React dashboard shell.
