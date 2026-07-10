# Dashboard Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `/dashboard` shell in `api_fortkentcinema_com` — pixel-identical leprinceos chrome (design system, Layout, Sidebar), `is_staff` auth, self-hosted fonts, HTMX/Alpine wiring, and reusable Toast/Confirm primitives — with a placeholder Home and stub routes, so later sub-projects drop their pages in.

**Architecture:** A new `dashboard` Django app with class-based views (`LoginRequiredMixin`/staff gate), a `base_dashboard.html` that reproduces `Layout.tsx`, sidebar/mobile-header partials driven by Alpine, and verbatim-ported CSS from the leprinceos SPA. No React. Interactivity via already-vendored HTMX + Alpine.

**Tech Stack:** Django 5.2, Python 3.13, HTMX + Alpine (vendored at `static/js/`), Django `TestCase`.

## Global Constraints

- Source of truth for pixel-perfect CSS/markup is the leprinceos SPA at `/Users/bgoding/code/SoftwareMaine/www_leprinceos_com`. Verbatim CSS ports must be exact copies (byte-for-byte rule text; classnames unchanged).
- Brand label is the literal string **"LeprinceOS"** (sidebar brand + mobile header). Do NOT rename.
- Nav items: **Home, Engagements, Screens** only. Do NOT include "API Docs".
- Auth gate is **`is_staff`**. Anonymous → redirect to `/login?next=…`; authenticated non-staff → HTTP 403.
- Fonts are **self-hosted** (woff2 vendored + `@font-face`); NO runtime Google Fonts/CDN `<link>`. If the environment cannot fetch the font files, report BLOCKED — do not fall back to a CDN link.
- All dashboard routes live under `/dashboard/`; URL namespace is `dashboard`.
- Tests use `django.test.TestCase`, run with `python manage.py test dashboard`.
- Run commands from repo root `api_fortkentcinema_com/` with the venv active: `source .venv/bin/activate`.
- Only create/modify files within `dashboard/` and the project files explicitly named in a task (`fortkentcinema/settings.py`, `fortkentcinema/urls.py`). Do NOT touch `web/`, `blog/`, `cinema/`, or `web/services/leprinceos.py`.

---

### Task 1: Scaffold `dashboard` app, auth gate, routing, minimal base

**Files:**
- Create: `dashboard/__init__.py`, `dashboard/apps.py`, `dashboard/urls.py`, `dashboard/views.py`, `dashboard/mixins.py`, `dashboard/migrations/__init__.py`, `dashboard/tests/__init__.py`
- Create: `dashboard/templates/dashboard/base_dashboard.html`, `dashboard/templates/dashboard/home.html`, `dashboard/templates/dashboard/_stub_page.html`
- Create: `dashboard/tests/test_auth.py`
- Modify: `fortkentcinema/settings.py` (INSTALLED_APPS, LOGIN_URL, LOGIN_REDIRECT_URL)
- Modify: `fortkentcinema/urls.py` (include dashboard.urls)

**Interfaces:**
- Produces: `StaffRequiredMixin` (in `dashboard/mixins.py`); named routes `dashboard:home`, `dashboard:screens`, `dashboard:engagements`; `base_dashboard.html` with `{% block content %}` and `{% block title %}`.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_auth.py`:

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class DashboardAuthTests(TestCase):
    def setUp(self) -> None:
        self.staff = User.objects.create_user(
            username="staffer", password="pw12345", is_staff=True
        )
        self.plain = User.objects.create_user(
            username="plain", password="pw12345", is_staff=False
        )

    def test_anonymous_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])
        self.assertIn("next=", resp["Location"])

    def test_non_staff_forbidden(self) -> None:
        self.client.login(username="plain", password="pw12345")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 403)

    def test_staff_ok(self) -> None:
        self.client.login(username="staffer", password="pw12345")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 200)

    def test_named_routes_resolve(self) -> None:
        self.assertEqual(reverse("dashboard:home"), "/dashboard/")
        self.assertEqual(reverse("dashboard:screens"), "/dashboard/screens")
        self.assertEqual(reverse("dashboard:engagements"), "/dashboard/engagements")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_auth -v 2`
Expected: FAIL — no `dashboard` app / `dashboard:home` not resolvable.

- [ ] **Step 3: Create the app package, mixin, views, urls**

`dashboard/__init__.py` — empty. `dashboard/migrations/__init__.py` — empty. `dashboard/tests/__init__.py` — empty.

`dashboard/apps.py`:

```python
from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"
```

`dashboard/mixins.py`:

```python
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse


class StaffRequiredMixin(AccessMixin):
    """Anonymous users are redirected to login; authenticated non-staff get 403."""

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
```

`dashboard/views.py`:

```python
from django.views.generic import TemplateView

from .mixins import StaffRequiredMixin


class HomeView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"


class ScreensStubView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/_stub_page.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Screens"
        return ctx


class EngagementsStubView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/_stub_page.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Engagements"
        return ctx
```

`dashboard/urls.py`:

```python
from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("screens", views.ScreensStubView.as_view(), name="screens"),
    path("engagements", views.EngagementsStubView.as_view(), name="engagements"),
]
```

- [ ] **Step 4: Create the minimal templates**

`dashboard/templates/dashboard/base_dashboard.html`:

```html
{% load static %}
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{% block title %}LeprinceOS{% endblock %}</title>
    {% block head_extra %}{% endblock %}
  </head>
  <body>
    <div class="layout">
      {% block chrome %}{% endblock %}
      <main class="main">
        <div class="container">
          {% block content %}{% endblock %}
        </div>
      </main>
    </div>
    {% block body_extra %}{% endblock %}
  </body>
</html>
```

`dashboard/templates/dashboard/home.html`:

```html
{% extends "dashboard/base_dashboard.html" %}
{% block title %}Home · LeprinceOS{% endblock %}
{% block content %}
  <div class="page-header">
    <div>
      <h1 class="page-title">Home</h1>
      <p class="page-subtitle">Dashboard overview</p>
    </div>
  </div>
{% endblock %}
```

`dashboard/templates/dashboard/_stub_page.html`:

```html
{% extends "dashboard/base_dashboard.html" %}
{% block title %}{{ page_title }} · LeprinceOS{% endblock %}
{% block content %}
  <div class="page-header">
    <div>
      <h1 class="page-title">{{ page_title }}</h1>
      <p class="page-subtitle">Coming soon</p>
    </div>
  </div>
{% endblock %}
```

- [ ] **Step 5: Wire settings and project urls**

In `fortkentcinema/settings.py`, add `"dashboard.apps.DashboardConfig"` to `INSTALLED_APPS` immediately after `"web.apps.WebConfig"`. Then add these two lines near the other auth-related settings (or at end of file):

```python
LOGIN_URL = "/login"
LOGIN_REDIRECT_URL = "/dashboard/"
```

In `fortkentcinema/urls.py`, add to `urlpatterns` (keep existing entries):

```python
    path("dashboard/", include("dashboard.urls")),
```

Ensure `include` and `path` are imported at the top: `from django.urls import path, include`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_auth -v 2`
Expected: PASS (4 tests). Then `python manage.py check` → no issues.

- [ ] **Step 7: Commit**

```bash
git add dashboard/ fortkentcinema/settings.py fortkentcinema/urls.py
git commit -m "feat(dashboard): scaffold dashboard app with is_staff gate and routes"
```

---

### Task 2: Self-hosted fonts

**Files:**
- Create: `dashboard/static/dashboard/fonts/` (woff2 files)
- Create: `dashboard/static/dashboard/css/fonts.css`
- Modify: `dashboard/templates/dashboard/base_dashboard.html` (link fonts.css)
- Create: `dashboard/tests/test_static_assets.py`

**Interfaces:**
- Produces: `fonts.css` defining `@font-face` for Plus Jakarta Sans (400,500,600,700), Playfair Display (400,600,700), Cormorant Garamond (400, 600, italic 400) — matching the exact families/weights the leprinceos `index.html` requested.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_static_assets.py`:

```python
from pathlib import Path

from django.conf import settings
from django.test import TestCase


FONTS_DIR = Path(settings.BASE_DIR) / "dashboard" / "static" / "dashboard" / "fonts"
CSS_DIR = Path(settings.BASE_DIR) / "dashboard" / "static" / "dashboard" / "css"


class FontAssetTests(TestCase):
    def test_fonts_css_exists_and_declares_families(self) -> None:
        css = (CSS_DIR / "fonts.css").read_text()
        self.assertIn("Plus Jakarta Sans", css)
        self.assertIn("Playfair Display", css)
        self.assertIn("Cormorant Garamond", css)
        self.assertIn("@font-face", css)
        # No runtime CDN reference
        self.assertNotIn("fonts.googleapis.com", css)
        self.assertNotIn("fonts.gstatic.com", css)

    def test_woff2_files_present(self) -> None:
        files = list(FONTS_DIR.glob("*.woff2"))
        self.assertGreaterEqual(len(files), 8)  # 4 + 3 + (2-3) weights
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_static_assets -v 2`
Expected: FAIL — `fonts.css` missing.

- [ ] **Step 3: Fetch the woff2 files**

Obtain the exact families/weights the SPA used (from `www_leprinceos_com/index.html`):
`Plus Jakarta Sans` wght 400;500;600;700 · `Playfair Display` wght 400;600;700 · `Cormorant Garamond` ital,wght 0,400;0,600;1,400.

Fetch each family's Latin woff2 via the Google Fonts CSS2 API using a modern browser User-Agent (this returns `@font-face` blocks pointing at `fonts.gstatic.com` woff2 URLs), then download those woff2 files into `dashboard/static/dashboard/fonts/`. Example for one family:

```bash
mkdir -p dashboard/static/dashboard/fonts
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
curl -s -A "$UA" \
  'https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap' \
  -o /tmp/pjs.css
# extract the latin woff2 URLs (the last src url in each @font-face for latin subset)
grep -oE 'https://fonts.gstatic.com/[^)]+\.woff2' /tmp/pjs.css | sort -u
```

Download one woff2 per weight per family into the fonts dir with descriptive names, e.g. `plus-jakarta-sans-400.woff2`, `plus-jakarta-sans-500.woff2`, …, `playfair-display-600.woff2`, `cormorant-garamond-400.woff2`, `cormorant-garamond-600.woff2`, `cormorant-garamond-italic-400.woff2`. Use the Latin subset file for each weight (the gstatic response lists multiple subsets; pick the block whose preceding `/* latin */` comment applies).

If the environment cannot reach `fonts.googleapis.com`/`fonts.gstatic.com`, STOP and report BLOCKED (per Global Constraints — do not add a CDN link).

- [ ] **Step 4: Write `fonts.css`**

Create `dashboard/static/dashboard/css/fonts.css` with one `@font-face` per downloaded file, e.g.:

```css
@font-face {
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url('../fonts/plus-jakarta-sans-400.woff2') format('woff2');
}
@font-face {
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url('../fonts/plus-jakarta-sans-500.woff2') format('woff2');
}
/* … 600, 700 … */
@font-face {
  font-family: 'Playfair Display';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url('../fonts/playfair-display-400.woff2') format('woff2');
}
/* … Playfair 600, 700 … */
@font-face {
  font-family: 'Cormorant Garamond';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url('../fonts/cormorant-garamond-400.woff2') format('woff2');
}
@font-face {
  font-family: 'Cormorant Garamond';
  font-style: normal;
  font-weight: 600;
  font-display: swap;
  src: url('../fonts/cormorant-garamond-600.woff2') format('woff2');
}
@font-face {
  font-family: 'Cormorant Garamond';
  font-style: italic;
  font-weight: 400;
  font-display: swap;
  src: url('../fonts/cormorant-garamond-italic-400.woff2') format('woff2');
}
```

Include every weight you downloaded (Plus Jakarta 400/500/600/700; Playfair 400/600/700; Cormorant normal 400/600 + italic 400).

- [ ] **Step 5: Link fonts.css in the base template head**

In `dashboard/templates/dashboard/base_dashboard.html`, add inside `<head>` (before `{% block head_extra %}`):

```html
    <link rel="stylesheet" href="{% static 'dashboard/css/fonts.css' %}" />
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_static_assets -v 2`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add dashboard/static/dashboard/fonts/ dashboard/static/dashboard/css/fonts.css dashboard/templates/dashboard/base_dashboard.html dashboard/tests/test_static_assets.py
git commit -m "feat(dashboard): self-host Plus Jakarta Sans, Playfair Display, Cormorant Garamond"
```

---

### Task 3: Design-system CSS (verbatim port)

**Files:**
- Create: `dashboard/static/dashboard/css/design-system.css`
- Modify: `dashboard/templates/dashboard/base_dashboard.html` (link design-system.css after fonts.css)
- Modify: `dashboard/tests/test_static_assets.py` (add sentinel assertions)

**Interfaces:**
- Produces: the global design-system stylesheet consumed by every dashboard page (tokens, `.btn*`, `.table`, `.page-header`, `.status-badge`, `.filter-tabs`, `.empty-state`, `.card`, utilities).

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_static_assets.py`:

```python
class DesignSystemCssTests(TestCase):
    def test_design_system_sentinels(self) -> None:
        css = (CSS_DIR / "design-system.css").read_text()
        for sentinel in ("--brass:", ".btn-primary", ".status-badge", ".page-header", ".empty-state"):
            self.assertIn(sentinel, css)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_static_assets.DesignSystemCssTests -v 2`
Expected: FAIL — `design-system.css` missing.

- [ ] **Step 3: Copy the design system CSS verbatim**

Copy the entire contents of `/Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/index.css` to `dashboard/static/dashboard/css/design-system.css` **unchanged** (do not retype — copy the bytes):

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/index.css \
   dashboard/static/dashboard/css/design-system.css
```

Do not edit the file. The `--font-sans/serif/display` variables reference the three families, which `fonts.css` (loaded first) now provides locally.

- [ ] **Step 4: Link design-system.css in the head**

In `base_dashboard.html`, add immediately AFTER the fonts.css link:

```html
    <link rel="stylesheet" href="{% static 'dashboard/css/design-system.css' %}" />
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_static_assets -v 2`
Expected: PASS (all asset tests).

- [ ] **Step 6: Commit**

```bash
git add dashboard/static/dashboard/css/design-system.css dashboard/templates/dashboard/base_dashboard.html dashboard/tests/test_static_assets.py
git commit -m "feat(dashboard): port leprinceos design-system CSS verbatim"
```

---

### Task 4: Layout + Sidebar chrome

**Files:**
- Create: `dashboard/static/dashboard/css/layout.css` (verbatim port)
- Create: `dashboard/static/dashboard/css/sidebar.css` (verbatim port)
- Create: `dashboard/static/dashboard/js/dashboard.js`
- Create: `dashboard/templates/dashboard/_sidebar.html`, `dashboard/templates/dashboard/_mobile_header.html`
- Create: `dashboard/templatetags/__init__.py`, `dashboard/templatetags/dashboard_nav.py`
- Modify: `dashboard/templates/dashboard/base_dashboard.html` (chrome block, layout Alpine root, CSS/JS links)
- Create: `dashboard/tests/test_chrome.py`

**Interfaces:**
- Consumes: `dashboard:home/screens/engagements` routes; vendored `static/js/alpine.min.js`.
- Produces: `{% nav_active request 'dashboard:home' %}` templatetag returning `"active"` or `""`; the rendered chrome (sidebar + mobile header) inside `base_dashboard.html`.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_chrome.py`:

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ChromeTests(TestCase):
    def setUp(self) -> None:
        self.staff = User.objects.create_user(
            username="staffer", password="pw12345", is_staff=True
        )
        self.client.login(username="staffer", password="pw12345")

    def test_brand_and_nav_items(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("LeprinceOS", html)
        self.assertIn(">Home<", html)
        self.assertIn(">Engagements<", html)
        self.assertIn(">Screens<", html)
        self.assertNotIn("API Docs", html)

    def test_logout_link_present(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn('href="/logout/"', html)

    def test_username_rendered(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("staffer", html)

    def test_active_nav_marked(self) -> None:
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        # the Screens link carries the active class on its own page
        self.assertRegex(html, r'href="/dashboard/screens"[^>]*class="[^"]*\bactive\b')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_chrome -v 2`
Expected: FAIL — nav/brand not rendered (base has empty chrome block).

- [ ] **Step 3: Create the nav_active templatetag**

`dashboard/templatetags/__init__.py` — empty.

`dashboard/templatetags/dashboard_nav.py`:

```python
from django import template
from django.urls import resolve

register = template.Library()


@register.simple_tag
def nav_active(request, url_name: str) -> str:
    """Return 'active' when the request's resolved URL name matches url_name.

    url_name is the fully-qualified name, e.g. 'dashboard:home'.
    """
    try:
        match = resolve(request.path_info)
    except Exception:
        return ""
    current = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
    return "active" if current == url_name else ""
```

- [ ] **Step 4: Port the chrome CSS verbatim**

Copy the two module CSS files verbatim (classnames unchanged):

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/components/Layout.module.css \
   dashboard/static/dashboard/css/layout.css
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/components/Sidebar.module.css \
   dashboard/static/dashboard/css/sidebar.css
```

(These contain some unused selector classes — e.g. `cinemaSelector*` in sidebar.css — which are harmless; keep them for fidelity.)

- [ ] **Step 5: Create the sidebar and mobile-header partials**

`dashboard/templates/dashboard/_mobile_header.html`:

```html
<header class="mobileHeader" x-show="!isFullscreen">
  <button class="mobileMenuToggle" @click="sidebarOpen = true" aria-label="Toggle navigation">
    <span class="hamburgerIcon"><span></span><span></span><span></span></span>
  </button>
  <a href="{% url 'dashboard:home' %}" class="mobileBrand">LeprinceOS</a>
</header>
```

`dashboard/templates/dashboard/_sidebar.html`:

```html
{% load static dashboard_nav %}
<div class="sidebarOverlay" x-show="sidebarOpen" @click="sidebarOpen = false" x-cloak></div>
<aside class="sidebar" :class="sidebarOpen ? 'sidebarOpen' : ''" data-cy="sidebar" x-show="!isFullscreen">
  <div class="sidebarBrand">
    <a href="{% url 'dashboard:home' %}" class="sidebarLogo" @click="sidebarOpen = false">LeprinceOS</a>
  </div>
  <nav class="sidebarNav" data-cy="sidebar-nav">
    <a href="{% url 'dashboard:home' %}" class="sidebarLink {% nav_active request 'dashboard:home' %}" @click="sidebarOpen = false">
      <svg class="sidebarIcon" width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M3 10.5L10 4l7 6.5V17a1 1 0 01-1 1h-4v-5H8v5H4a1 1 0 01-1-1v-6.5z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      Home
    </a>
    <a href="{% url 'dashboard:engagements' %}" class="sidebarLink {% nav_active request 'dashboard:engagements' %}" @click="sidebarOpen = false">
      <svg class="sidebarIcon" width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M7 8h6M7 12h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      Engagements
    </a>
    <a href="{% url 'dashboard:screens' %}" class="sidebarLink {% nav_active request 'dashboard:screens' %}" @click="sidebarOpen = false">
      <svg class="sidebarIcon" width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="3" width="16" height="11" rx="1" stroke="currentColor" stroke-width="1.5"/><path d="M7 17h6M10 14v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      Screens
    </a>
  </nav>
  <div class="sidebarUser" data-cy="sidebar-user">
    <div class="sidebarUserInfo">
      <span class="sidebarUsername" data-cy="username">{{ request.user.username }}</span>
    </div>
    <a class="sidebarLogout" href="/logout/" data-cy="logout-button">
      <svg class="sidebarIcon" width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M7 17H4a1 1 0 01-1-1V4a1 1 0 011-1h3M13 14l4-4-4-4M17 10H7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      Log Out
    </a>
  </div>
</aside>
```

Note the active class matches the source's `sidebarLink active` pattern; the `nav_active` tag emits `active` (or empty). The test regex tolerates the trailing space.

- [ ] **Step 6: Create dashboard.js (Alpine layout component + Alt+N)**

`dashboard/static/dashboard/js/dashboard.js`:

```javascript
// Dashboard chrome behaviour: sidebar toggle, fullscreen, keyboard shortcut.
document.addEventListener('alpine:init', () => {
  Alpine.data('dashboardLayout', () => ({
    sidebarOpen: false,
    isFullscreen: false,
    toggleFullscreen() {
      this.isFullscreen = !this.isFullscreen;
      if (this.isFullscreen) {
        document.documentElement.requestFullscreen?.().catch(() => {});
      } else {
        document.exitFullscreen?.().catch(() => {});
      }
    },
    init() {
      document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement) this.isFullscreen = false;
      });
    },
  }));
});

// Alt+N -> go to engagements (create-drawer wiring lands in the Engagements sub-project).
document.addEventListener('keydown', (e) => {
  const el = document.activeElement;
  const typing =
    el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.hasAttribute('contenteditable'));
  if (typing) return;
  if (e.altKey && (e.key === 'n' || e.key === 'N')) {
    e.preventDefault();
    window.location.href = '/dashboard/engagements';
  }
});
```

- [ ] **Step 7: Wire chrome into base_dashboard.html**

Rewrite `dashboard/templates/dashboard/base_dashboard.html` to load chrome CSS/JS, put the Alpine layout root on `.layout`, and fill the chrome block:

```html
{% load static %}
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{% block title %}LeprinceOS{% endblock %}</title>
    <link rel="stylesheet" href="{% static 'dashboard/css/fonts.css' %}" />
    <link rel="stylesheet" href="{% static 'dashboard/css/design-system.css' %}" />
    <link rel="stylesheet" href="{% static 'dashboard/css/layout.css' %}" />
    <link rel="stylesheet" href="{% static 'dashboard/css/sidebar.css' %}" />
    <style>[x-cloak]{display:none !important;}</style>
    {% block head_extra %}{% endblock %}
    <script defer src="{% static 'js/alpine.min.js' %}"></script>
    <script defer src="{% static 'js/htmx.min.js' %}"></script>
    <script defer src="{% static 'dashboard/js/dashboard.js' %}"></script>
  </head>
  <body>
    <div class="layout" x-data="dashboardLayout">
      {% include "dashboard/_mobile_header.html" %}
      {% include "dashboard/_sidebar.html" %}
      <main :class="isFullscreen ? 'mainFullscreen' : 'main'">
        <div :class="isFullscreen ? 'containerFullscreen' : 'container'">
          {% block content %}{% endblock %}
        </div>
        <div class="keyboardHint" x-show="!isFullscreen" title="Press Alt+N to create new engagement">
          <kbd class="kbd">Alt+N</kbd>
          <span class="hintText">New Engagement</span>
        </div>
      </main>
    </div>
    {% block body_extra %}{% endblock %}
  </body>
</html>
```

Note: `dashboard.js` must load AFTER alpine.min.js so `alpine:init` binds; but `alpine.min.js` is deferred and dispatches `alpine:init` on its own start — using `defer` on all three preserves document order (alpine, then htmx, then dashboard.js), and `dashboard.js` registers its `alpine:init` listener before Alpine initializes because listener registration in a deferred script runs before Alpine's deferred init only if ordered first. To be safe, Alpine must be LAST so its init fires after `dashboard.js` has registered the listener. **Correction:** order the scripts as `dashboard.js`, `htmx.min.js`, then `alpine.min.js` LAST:

```html
    <script defer src="{% static 'dashboard/js/dashboard.js' %}"></script>
    <script defer src="{% static 'js/htmx.min.js' %}"></script>
    <script defer src="{% static 'js/alpine.min.js' %}"></script>
```

Use this corrected order in the final file.

- [ ] **Step 8: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_chrome -v 2`
Expected: PASS (4 tests). Also run `python manage.py test dashboard -v 1` → all green; `python manage.py check` → no issues.

- [ ] **Step 9: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): Layout + Sidebar chrome (Alpine) with active nav"
```

---

### Task 5: Toast + Confirm primitives

**Files:**
- Create: `dashboard/static/dashboard/css/alertbanner.css` (verbatim port)
- Create: `dashboard/static/dashboard/css/confirm.css` (verbatim port of ConfirmDialog.module.css)
- Create: `dashboard/templates/dashboard/_toast.html`, `dashboard/templates/dashboard/_confirm.html`
- Modify: `dashboard/static/dashboard/js/dashboard.js` (toast + confirm Alpine stores + window helpers)
- Modify: `dashboard/templates/dashboard/base_dashboard.html` (include primitives + link CSS)
- Create: `dashboard/tests/test_primitives.py`

**Interfaces:**
- Consumes: Alpine (loaded in base).
- Produces: `window.dashboardToast(kind, message)` (kind ∈ warning|info|success|error) and `window.dashboardConfirm({title, message, confirmLabel, variant})` returning a `Promise<boolean>`; the `_toast.html` and `_confirm.html` includes rendered once in the layout.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_primitives.py`:

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class PrimitiveTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_toast_and_confirm_regions_rendered(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        # toast region + confirm dialog scaffolding present on every page
        self.assertIn('class="alertContainer"', html)
        self.assertIn("$store.toast", html)
        self.assertIn("$store.confirm", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_primitives -v 2`
Expected: FAIL — primitives not included.

- [ ] **Step 3: Port the primitive CSS verbatim**

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/components/AlertBanner.module.css \
   dashboard/static/dashboard/css/alertbanner.css
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/contexts/ConfirmDialog.module.css \
   dashboard/static/dashboard/css/confirm.css
```

- [ ] **Step 4: Add toast + confirm Alpine stores and window helpers to dashboard.js**

Append to `dashboard/static/dashboard/js/dashboard.js`, inside a new `alpine:init` listener (or extend the existing one — keep the `Alpine.data('dashboardLayout', …)` registration too):

```javascript
document.addEventListener('alpine:init', () => {
  // Toast store — mirrors ToastContext (auto-dismiss 6s).
  Alpine.store('toast', {
    items: [],
    add(kind, message) {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      this.items.push({ id, kind, message });
      setTimeout(() => this.dismiss(id), 6000);
    },
    dismiss(id) {
      this.items = this.items.filter((t) => t.id !== id);
    },
    icon(kind) {
      return { warning: '⚠', info: 'ℹ', success: '✓', error: '✕' }[kind] || 'ℹ';
    },
  });

  // Confirm store — mirrors ConfirmContext (promise-based, ESC cancels).
  Alpine.store('confirm', {
    open: false,
    title: '',
    message: '',
    confirmLabel: 'Confirm',
    variant: 'default',
    _resolve: null,
    ask({ title, message, confirmLabel = 'Confirm', variant = 'default' }) {
      this.title = title;
      this.message = message;
      this.confirmLabel = confirmLabel;
      this.variant = variant;
      this.open = true;
      document.body.style.overflow = 'hidden';
      return new Promise((resolve) => {
        this._resolve = resolve;
      });
    },
    _settle(value) {
      this.open = false;
      document.body.style.overflow = '';
      const r = this._resolve;
      this._resolve = null;
      if (r) r(value);
    },
    accept() {
      this._settle(true);
    },
    cancel() {
      this._settle(false);
    },
  });
});

window.dashboardToast = (kind, message) => window.Alpine?.store('toast').add(kind, message);
window.dashboardConfirm = (opts) => window.Alpine.store('confirm').ask(opts);
```

- [ ] **Step 5: Create the toast and confirm includes**

`dashboard/templates/dashboard/_toast.html` (structure + classnames from `AlertBanner.tsx`):

```html
<div class="alertContainer" x-show="$store.toast.items.length > 0" x-cloak>
  <template x-for="alert in $store.toast.items" :key="alert.id">
    <div role="alert" aria-live="polite"
         class="alert"
         :class="{ alertWarning: alert.kind==='warning', alertInfo: alert.kind==='info', alertSuccess: alert.kind==='success', alertError: alert.kind==='error' }">
      <div class="alertIcon" x-text="$store.toast.icon(alert.kind)"></div>
      <p class="alertMessage" x-text="alert.message"></p>
      <button type="button" class="dismissButton" aria-label="Dismiss alert" @click="$store.toast.dismiss(alert.id)">
        <span aria-hidden="true">&times;</span>
      </button>
    </div>
  </template>
</div>
```

`dashboard/templates/dashboard/_confirm.html` (structure + classnames from `ConfirmContext.tsx`):

```html
<div class="overlay" x-show="$store.confirm.open" x-cloak
     @keydown.escape.window="$store.confirm.open && $store.confirm.cancel()"
     @click="$store.confirm.cancel()">
  <div class="dialog" @click.stop role="alertdialog" aria-modal="true"
       aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-message" tabindex="-1">
    <div class="header">
      <h2 id="confirm-dialog-title" class="title" x-text="$store.confirm.title"></h2>
    </div>
    <div class="body">
      <p id="confirm-dialog-message" class="message" x-text="$store.confirm.message"></p>
    </div>
    <div class="footer">
      <button type="button" class="cancelButton" data-confirm-cancel @click="$store.confirm.cancel()">Cancel</button>
      <button type="button" class="confirmButton" :class="{ danger: $store.confirm.variant==='danger' }"
              data-confirm-ok @click="$store.confirm.accept()" x-text="$store.confirm.confirmLabel"></button>
    </div>
  </div>
</div>
```

(Prompt/textarea mode from the source is not needed by any Foundation consumer; add it in a later sub-project if a page requires `prompt`.)

- [ ] **Step 6: Wire primitives + CSS into base_dashboard.html**

Add the two CSS links in `<head>` after sidebar.css:

```html
    <link rel="stylesheet" href="{% static 'dashboard/css/alertbanner.css' %}" />
    <link rel="stylesheet" href="{% static 'dashboard/css/confirm.css' %}" />
```

Inside `<main>`, put the toast region just above `{% block content %}`’s container, and include the confirm dialog once near the end of `.layout` (before closing `</div>` of `.layout`):

```html
        {% include "dashboard/_toast.html" %}
        {% block content %}{% endblock %}
```

and, just before `</div>` that closes `.layout`:

```html
      {% include "dashboard/_confirm.html" %}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_primitives -v 2`
Expected: PASS. Then `python manage.py test dashboard -v 1` → all green.

- [ ] **Step 8: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): reusable Alpine Toast + Confirm primitives"
```

---

### Task 6: Themed login / logout

**Files:**
- Create: `dashboard/templates/dashboard/login.html`
- Create: `dashboard/static/dashboard/css/login.css`
- Modify: `fortkentcinema/urls.py` (login + logout routes)
- Create: `dashboard/tests/test_login.py`

**Interfaces:**
- Consumes: Django auth views; the design-system + fonts CSS.
- Produces: `/login` (themed `LoginView`) and `/logout/` (`LogoutView`).

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_login.py`:

```python
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class LoginTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="staffer", password="pw12345", is_staff=True)

    def test_login_page_themed(self) -> None:
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("LeprinceOS", html)
        self.assertIn("login.css", html)

    def test_login_redirects_to_dashboard(self) -> None:
        resp = self.client.post(
            "/login", {"username": "staffer", "password": "pw12345"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/dashboard/")

    def test_logout_works(self) -> None:
        self.client.login(username="staffer", password="pw12345")
        resp = self.client.post("/logout/")
        self.assertEqual(resp.status_code, 302)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_login -v 2`
Expected: FAIL — `/login` not routed / template missing.

- [ ] **Step 3: Create the themed login template**

`dashboard/templates/dashboard/login.html`:

```html
{% load static %}
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sign in · LeprinceOS</title>
    <link rel="stylesheet" href="{% static 'dashboard/css/fonts.css' %}" />
    <link rel="stylesheet" href="{% static 'dashboard/css/design-system.css' %}" />
    <link rel="stylesheet" href="{% static 'dashboard/css/login.css' %}" />
  </head>
  <body class="login-body">
    <main class="login-shell">
      <div class="login-card card">
        <div class="login-brand">LeprinceOS</div>
        <p class="login-subtitle">Cinema Management</p>
        {% if form.errors %}
          <div class="login-error">Invalid username or password.</div>
        {% endif %}
        <form method="post" action="{% url 'login' %}" class="login-form">
          {% csrf_token %}
          <input type="hidden" name="next" value="{{ next }}" />
          <label class="login-label" for="id_username">Username</label>
          {{ form.username }}
          <label class="login-label" for="id_password">Password</label>
          {{ form.password }}
          <button type="submit" class="btn btn-primary login-submit">Sign In</button>
        </form>
      </div>
    </main>
  </body>
</html>
```

- [ ] **Step 4: Create login.css (themed, using design tokens)**

`dashboard/static/dashboard/css/login.css`:

```css
.login-body {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--charcoal);
  padding: var(--space-lg);
}
.login-shell { width: 100%; max-width: 400px; }
.login-card { padding: var(--space-2xl); animation: scale-in 0.4s ease-out; }
.login-brand {
  font-family: var(--font-serif);
  font-size: var(--text-3xl);
  font-weight: 600;
  color: var(--text-primary);
  text-align: center;
}
.login-subtitle {
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-bottom: var(--space-xl);
}
.login-form { display: flex; flex-direction: column; gap: var(--space-sm); }
.login-label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin-top: var(--space-sm);
}
.login-form input[type="text"],
.login-form input[type="password"] {
  width: 100%;
  padding: var(--space-md);
  font-family: var(--font-sans);
  font-size: var(--text-base);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--surface-elevated);
  color: var(--text-primary);
}
.login-form input:focus-visible { outline: 2px solid var(--brass); outline-offset: 2px; }
.login-submit { width: 100%; margin-top: var(--space-lg); }
.login-error {
  background: var(--status-cancelled-bg);
  color: var(--status-cancelled);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  margin-bottom: var(--space-md);
  text-align: center;
}
```

- [ ] **Step 5: Route login + logout at project level**

In `fortkentcinema/urls.py`, add imports and routes:

```python
from django.contrib.auth.views import LoginView, LogoutView
```

and in `urlpatterns` (before the dashboard include is fine):

```python
    path("login", LoginView.as_view(template_name="dashboard/login.html"), name="login"),
    path("logout/", LogoutView.as_view(next_page="/login"), name="logout"),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_login -v 2`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add dashboard/templates/dashboard/login.html dashboard/static/dashboard/css/login.css fortkentcinema/urls.py dashboard/tests/test_login.py
git commit -m "feat(dashboard): themed login and logout"
```

---

### Task 7: Final verification

**Files:** none (verification only).

- [ ] **Step 1: System + migration checks**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Run: `python manage.py makemigrations --check --dry-run`
Expected: `No changes detected` (the dashboard app defines no models).

- [ ] **Step 2: Full dashboard suite**

Run: `python manage.py test dashboard -v 2`
Expected: PASS (auth, static assets, chrome, primitives, login).

- [ ] **Step 3: Whole project suite (no regressions)**

Run: `python manage.py test`
Expected: PASS — existing `web`/`blog`/`cinema` suites unaffected; new `dashboard` tests included.

- [ ] **Step 4: Manual browser smoke (recommended)**

`python manage.py runserver`, log in as a staff user at `/login`, then at `/dashboard/` confirm: sidebar renders with LeprinceOS brand + Home/Engagements/Screens (no API Docs), active nav highlights, mobile hamburger opens the sidebar with overlay, fullscreen toggle hides chrome, `window.dashboardToast('success','Saved')` shows a toast that auto-dismisses, `await window.dashboardConfirm({title:'Delete?',message:'Sure?',variant:'danger'})` shows the themed dialog. No console errors. Compare side-by-side with the React dashboard shell (`www_leprinceos_com` `npm run dev`).

---

## Self-Review

**Spec coverage:**
- `dashboard` app + `/dashboard/` mount + is_staff gate → Task 1. ✅
- Self-hosted fonts (exact families/weights) → Task 2. ✅
- Verbatim design-system CSS → Task 3. ✅
- Layout + Sidebar chrome (Alpine, active nav, no API Docs, LeprinceOS brand, logout) → Task 4. ✅
- Toast + Confirm primitives (reusable) → Task 5. ✅
- Themed login + logout, LOGIN_URL wiring → Tasks 1 (settings) + 6. ✅
- Stub Screens/Engagements routes → Task 1. ✅
- HTMX + Alpine wiring → Task 4 base template. ✅
- Testing (auth, chrome, assets, primitives, login) + verification → Tasks 1–7. ✅
- Out-of-scope items (cinema CRUD, FilmSearch, StatusDropdown, smart alerts, Showtimes) → not present in any task. ✅

**Placeholder scan:** No TBD/"add error handling"/vague steps; all code inlined except the four verbatim CSS copies, which are exact `cp` from named source files (complete content by reference). `forms.py` intentionally omitted (no forms in Foundation).

**Type consistency:** `nav_active(request, url_name)` signature matches its template calls. `window.dashboardToast(kind, message)` / `window.dashboardConfirm({title,message,confirmLabel,variant})` match the store methods (`toast.add(kind,message)`, `confirm.ask({...})`). Alpine store names (`$store.toast`, `$store.confirm`) match between dashboard.js and the includes. `.layout`/`.main`/`.sidebar`/`.mobileHeader` classnames match the verbatim-ported CSS. Script load order corrected to dashboard.js → htmx → alpine (alpine last) so the `alpine:init` listeners are registered first.
