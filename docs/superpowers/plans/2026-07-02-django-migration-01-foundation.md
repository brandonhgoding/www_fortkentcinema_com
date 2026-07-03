# Django Migration — Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the server-rendered shell of `fortkentcinema.com` inside the existing `api_fortkentcinema_com` Django project — a `web` app, a `base.html` carrying all global chrome/meta/SEO, the pure-CSS design system ported verbatim, the visual-effects JS build pipeline (ambient dust + scroll reveal), and deploy-ready static settings — so later plans only add pages.

**Architecture:** A new `web` Django app renders pages with class-based views against a project-level `templates/` dir. `base.html` owns the `<head>` (overridable meta/OG blocks + `MovieTheater` JSON-LD + GA) and the page chrome (vignette, curtains, skip-link, ambient-dust canvas, nav/footer placeholders). Pure CSS is copied unchanged into `static/css/`. A small Vite build compiles the framework-agnostic effects `core/` plus vanilla `init*` modules into `static/js/effects.js`, booted with the same motion-tier guards as the React app.

**Tech Stack:** Django 5.2.3, Django templates, class-based views, pure CSS (no Tailwind), Vite + Vitest + d3-timer for the effects bundle, WhiteNoise for static serving. Tests: Django `unittest` (`manage.py test`) + Vitest for JS.

## Global Constraints

- Target repo: `api_fortkentcinema_com`. Work branch: `feat/django-frontend-migration` (already created).
- Django **5.2.3**, DRF **3.16.0** — the existing `api/` DRF surface must keep working untouched.
- Settings read env via `python-decouple` `config(...)` — follow the existing pattern in `fortkentcinema/settings.py`.
- `TIME_ZONE = "America/New_York"`, `USE_TZ = True` — already set; do not change.
- leprinceos API base URL (used in later plans): `https://www.leprinceos.com/api/v1`.
- Google Analytics measurement ID: `G-S2PR27SWGD` (verbatim from the SPA's `index.html`).
- CSS is **ported verbatim** from `www_fortkentcinema_com` — never edit the visual rules; the acceptance bar is pixel-identical output.
- No React, no Tailwind, no Flowbite. Pure CSS only.
- Effects must honor the SPA's motion tiers via `getMotionTier()` (`static` / `ambient` / `full`) — copied verbatim, not reinterpreted.
- Views are class-based wherever a generic view fits.
- TDD: write the failing test first every time. Commit after each green task.
- SPA source to port from lives at `../www_fortkentcinema_com` relative to the Django repo.

---

### Task 1: Scaffold `web` app + minimal base template + placeholder home route

Creates the app, project `templates/` dir, a skeletal `base.html`, a placeholder `HomeView` at `/`, and wires URLs. The homepage content is a placeholder here — **Plan 2 replaces `HomeView` with the real homepage + leprinceos service.**

**Files:**
- Create: `web/__init__.py`, `web/apps.py`, `web/views.py`, `web/urls.py`, `web/tests/__init__.py`, `web/tests/test_pages.py`
- Create: `templates/base.html`, `web/templates/web/home.html`
- Modify: `fortkentcinema/settings.py` (INSTALLED_APPS, TEMPLATES `DIRS`)
- Modify: `fortkentcinema/urls.py` (include `web.urls` at `/`)

**Interfaces:**
- Produces: `web.views.HomeView` (a `TemplateView`, `template_name = "web/home.html"`); URL name `home` at path `""`; project template `base.html` with blocks `title`, `description`, `og_title`, `og_description`, `og_image`, `og_type`, `content`.

- [ ] **Step 1: Write the failing test**

Create `web/tests/__init__.py` (empty) and `web/tests/test_pages.py`:

```python
from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_home_returns_200(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_home_uses_base_and_home_templates(self):
        response = self.client.get(reverse("home"))
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/home.html")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python manage.py test web`
Expected: FAIL — `django.urls.exceptions.NoReverseMatch: Reverse for 'home' not found` (URL/app not created yet).

- [ ] **Step 3: Create the `web` app package**

Create `web/__init__.py` (empty) and `web/apps.py`:

```python
from django.apps import AppConfig


class WebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "web"
```

Create `web/views.py`:

```python
from django.views.generic import TemplateView


class HomeView(TemplateView):
    # Placeholder shell — Plan 2 replaces this with the real homepage
    # (Hero, NowShowing, ComingSoon, Membership) backed by the leprinceos service.
    template_name = "web/home.html"
```

Create `web/urls.py`:

```python
from django.urls import path

from .views import HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
]
```

- [ ] **Step 4: Register the app and template dir in settings**

In `fortkentcinema/settings.py`, add `web` to `INSTALLED_APPS` (after `blog.apps.BlogConfig`):

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "blog.apps.BlogConfig",
    "web.apps.WebConfig",
    "rest_framework",
    "corsheaders",
]
```

In the same file, point `TEMPLATES[0]["DIRS"]` at a project-level `templates/` dir:

```python
        "DIRS": [BASE_DIR / "templates"],
```

- [ ] **Step 5: Wire the URLconf**

In `fortkentcinema/urls.py`, add the `web.urls` include **last** (so `admin/` and `api/` match first):

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("blog.urls")),
    path("", include("web.urls")),
]
```

- [ ] **Step 6: Create the skeletal base + home templates**

Create `templates/base.html` (expanded fully in Task 3 — skeletal for now):

```django
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{% block title %}Fort Kent Cinema{% endblock %}</title>
    <meta name="description" content="{% block description %}Maine's Northernmost Picture Show{% endblock %}" />
  </head>
  <body>
    <main id="main-content">
      {% block content %}{% endblock %}
    </main>
  </body>
</html>
```

Create `web/templates/web/home.html`:

```django
{% extends "base.html" %}

{% block title %}Fort Kent Cinema | Maine's Northernmost Picture Show{% endblock %}

{% block content %}
  <h1>Fort Kent Cinema</h1>
{% endblock %}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `python manage.py test web`
Expected: PASS (2 tests, OK).

- [ ] **Step 8: Commit**

```bash
git add web/ templates/base.html fortkentcinema/settings.py fortkentcinema/urls.py
git commit -m "feat(web): scaffold web app, base template, placeholder home route"
```

---

### Task 2: Site config constants + context processor

Ports `siteConfig.json` (and `membership.json`, needed by a later plan) into Python and exposes `site_config` to every template, so `base.html`'s nav/footer/JSON-LD have data.

**Files:**
- Create: `web/constants.py`, `web/context_processors.py`
- Modify: `fortkentcinema/settings.py` (add context processor)
- Modify: `web/tests/test_pages.py` (add tests)
- Reference (read, do not import): `../www_fortkentcinema_com/src/data/siteConfig.json`, `../www_fortkentcinema_com/src/data/membership.json`

**Interfaces:**
- Produces: `web.constants.SITE_CONFIG` (dict with keys `cinema`, `hours`, `social`, `navigation`) and `web.constants.MEMBERSHIP` (the ported membership tiers, consumed by the Membership plan); `web.context_processors.site_config(request)` returning `{"site_config": SITE_CONFIG}`.

- [ ] **Step 1: Write the failing test**

Add to `web/tests/test_pages.py`:

```python
class SiteConfigContextTests(TestCase):
    def test_site_config_available_in_templates(self):
        response = self.client.get(reverse("home"))
        self.assertIn("site_config", response.context)
        self.assertEqual(
            response.context["site_config"]["cinema"]["name"], "Fort Kent Cinema"
        )

    def test_navigation_present(self):
        from web.constants import SITE_CONFIG

        labels = [item["label"] for item in SITE_CONFIG["navigation"]]
        self.assertIn("Now Showing", labels)
        self.assertIn("Blog", labels)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python manage.py test web`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.constants'`.

- [ ] **Step 3: Create the constants module**

Read `../www_fortkentcinema_com/src/data/siteConfig.json` and `../www_fortkentcinema_com/src/data/membership.json` and transcribe them as Python literals. Create `web/constants.py`:

```python
# Ported verbatim from the React SPA's src/data/siteConfig.json.
SITE_CONFIG = {
    "cinema": {
        "name": "Fort Kent Cinema",
        "tagline": "Maine's Northernmost Picture Show",
        "heroQuote": "Where the movies come to life under the northern lights",
        "address": {
            "street": "13 Hall Street",
            "city": "Fort Kent",
            "state": "ME",
            "zip": "04743",
        },
        "phone": "(207) 231-5287",
    },
    "hours": {
        "weekday": {"days": "Monday - Thursday", "open": "4:00 PM", "close": "9:00 PM"},
        "weekend": {"days": "Friday - Sunday", "open": "2:00 PM", "close": "10:00 PM"},
    },
    "social": {"facebook": "https://facebook.com/fortkentcinema"},
    "navigation": [
        {"label": "Now Showing", "href": "#now-showing"},
        {"label": "Coming Soon", "href": "#coming-soon"},
        {"label": "Classics", "href": "/classics"},
        {"label": "Membership", "href": "/membership"},
        {"label": "Rentals", "href": "/rentals"},
        {"label": "About", "href": "/about"},
        {"label": "Blog", "href": "/blog"},
    ],
}

# Ported verbatim from the React SPA's src/data/membership.json.
# Consumed by the Membership page plan; transcribe the full file contents here.
MEMBERSHIP = {}  # <-- replace {} with the transcribed membership.json object
```

Note: transcribe the **entire** `membership.json` object into `MEMBERSHIP` (do not leave `{}`); it is used by a later plan but ported now while the source is in hand.

- [ ] **Step 4: Create the context processor**

Create `web/context_processors.py`:

```python
from .constants import SITE_CONFIG


def site_config(request):
    return {"site_config": SITE_CONFIG}
```

- [ ] **Step 5: Register the context processor**

In `fortkentcinema/settings.py`, add to `TEMPLATES[0]["OPTIONS"]["context_processors"]`:

```python
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "web.context_processors.site_config",
            ],
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python manage.py test web`
Expected: PASS (all tests OK).

- [ ] **Step 7: Commit**

```bash
git add web/constants.py web/context_processors.py fortkentcinema/settings.py web/tests/test_pages.py
git commit -m "feat(web): port site config + membership constants and context processor"
```

---

### Task 3: Full base.html — meta/OG blocks, JSON-LD, GA, page chrome

Expands `base.html` into the complete global shell: overridable meta/OG blocks (default values from the SPA `index.html`), the `MovieTheater` JSON-LD, Google Analytics, favicon/theme-color/geo/Twitter tags, and the chrome (vignette, curtains, skip-link, ambient-dust canvas, nav/footer placeholder includes).

**Files:**
- Modify: `templates/base.html`
- Create: `templates/partials/nav.html`, `templates/partials/footer.html` (placeholders; real markup in later page plans)
- Modify: `web/tests/test_pages.py`
- Reference (read): `../www_fortkentcinema_com/index.html`, `../www_fortkentcinema_com/src/App.jsx` (chrome markup: `vignette`, `curtain-left/right`, `skip-link`, `AmbientDust`)

**Interfaces:**
- Produces: `base.html` blocks `meta`, `title`, `description`, `og_title`, `og_description`, `og_image`, `og_type`, `extra_head`, `extra_css`, `content`, `extra_js`. Chrome elements: `<canvas class="fx-dust" data-ambient-dust>`, `.vignette`, `.curtain-left`, `.curtain-right`, `a.skip-link`. Partial include points: `partials/nav.html`, `partials/footer.html`.

- [ ] **Step 1: Write the failing test**

Add to `web/tests/test_pages.py`:

```python
class BaseChromeTests(TestCase):
    def test_default_meta_and_og(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode()
        self.assertIn('property="og:title"', html)
        self.assertIn('property="og:type"', html)
        self.assertIn('name="twitter:card"', html)

    def test_structured_data_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('"@type": "MovieTheater"', html)
        self.assertIn("13 Hall Street", html)

    def test_google_analytics_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("G-S2PR27SWGD", html)

    def test_chrome_elements_present(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="skip-link"', html)
        self.assertIn("fx-dust", html)
        self.assertIn("data-ambient-dust", html)

    def test_canonical_uses_request_url(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('rel="canonical"', html)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python manage.py test web`
Expected: FAIL — `AssertionError: 'property="og:title"' not found` (skeletal base has no OG tags).

- [ ] **Step 3: Write the full base.html**

Replace `templates/base.html` entirely:

```django
{% load static %}<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />

    {% block meta %}
    <title>{% block title %}Fort Kent Cinema | Maine's Northernmost Picture Show{% endblock %}</title>
    <meta name="description" content="{% block description %}Fort Kent Cinema - Maine's Northernmost Picture Show. View current showtimes, upcoming movies, buy tickets, and join our Cinema Club membership program. Located at 13 Hall Street, Fort Kent, ME.{% endblock %}" />
    <meta name="author" content="Fort Kent Cinema" />
    <meta name="robots" content="index, follow" />
    <meta name="theme-color" content="#0a0a0e" />
    <link rel="canonical" href="{{ request.build_absolute_uri }}" />

    <meta property="og:type" content="{% block og_type %}website{% endblock %}" />
    <meta property="og:url" content="{{ request.build_absolute_uri }}" />
    <meta property="og:title" content="{% block og_title %}Fort Kent Cinema | Maine's Northernmost Picture Show{% endblock %}" />
    <meta property="og:description" content="{% block og_description %}View current showtimes, upcoming movies, and join our Cinema Club membership. Maine's Northernmost Picture Show in Fort Kent.{% endblock %}" />
    <meta property="og:image" content="{% block og_image %}https://www.fortkentcinema.com/og-image.jpg{% endblock %}" />
    <meta property="og:locale" content="en_US" />
    <meta property="og:site_name" content="Fort Kent Cinema" />

    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{{ self.og_title }}" />
    <meta name="twitter:description" content="{{ self.og_description }}" />
    <meta name="twitter:image" content="{{ self.og_image }}" />

    <meta name="geo.region" content="US-ME" />
    <meta name="geo.placename" content="Fort Kent" />
    <meta name="geo.position" content="47.2586;-68.5894" />
    <meta name="ICBM" content="47.2586, -68.5894" />
    {% endblock %}

    <link rel="icon" type="image/svg+xml" href="{% static 'img/favicon.svg' %}" />
    <link rel="apple-touch-icon" href="{% static 'img/favicon.svg' %}" />

    <link rel="stylesheet" href="{% static 'css/global.css' %}" />
    <link rel="stylesheet" href="{% static 'css/effects.css' %}" />
    {% block extra_css %}{% endblock %}

    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "MovieTheater",
      "name": "{{ site_config.cinema.name }}",
      "description": "Maine's Northernmost Picture Show - a community cinema in Fort Kent featuring current movies, special events, and Cinema Club membership.",
      "url": "https://www.fortkentcinema.com",
      "telephone": "{{ site_config.cinema.phone }}",
      "address": {
        "@type": "PostalAddress",
        "streetAddress": "{{ site_config.cinema.address.street }}",
        "addressLocality": "{{ site_config.cinema.address.city }}",
        "addressRegion": "{{ site_config.cinema.address.state }}",
        "postalCode": "{{ site_config.cinema.address.zip }}",
        "addressCountry": "US"
      },
      "geo": {"@type": "GeoCoordinates", "latitude": 47.2586, "longitude": -68.5894},
      "sameAs": ["{{ site_config.social.facebook }}"],
      "priceRange": "$$",
      "currenciesAccepted": "USD",
      "paymentAccepted": "Cash, Credit Card"
    }
    </script>

    <script async src="https://www.googletagmanager.com/gtag/js?id=G-S2PR27SWGD"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-S2PR27SWGD');
    </script>

    {% block extra_head %}{% endblock %}
  </head>
  <body>
    <div class="vignette"></div>
    <canvas class="fx-dust" data-ambient-dust aria-hidden="true"></canvas>
    <div class="curtain-left"></div>
    <div class="curtain-right"></div>
    <a href="#main-content" class="skip-link">Skip to main content</a>

    {% include "partials/nav.html" %}

    <main id="main-content">
      {% block content %}{% endblock %}
    </main>

    {% include "partials/footer.html" %}

    <script type="module" src="{% static 'js/effects.js' %}"></script>
    {% block extra_js %}{% endblock %}
  </body>
</html>
```

- [ ] **Step 4: Create placeholder nav/footer partials**

Create `templates/partials/nav.html`:

```django
{# Placeholder — real nav markup ported in the Home page plan #}
<nav class="nav" data-nav></nav>
```

Create `templates/partials/footer.html`:

```django
{# Placeholder — real footer markup ported in the Home page plan #}
<footer class="footer" data-footer></footer>
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python manage.py test web`
Expected: PASS. (The `effects.js`/`global.css` static files don't exist yet; `{% static %}` only builds a URL, so template rendering still succeeds. Those files land in Tasks 4–5.)

- [ ] **Step 6: Commit**

```bash
git add templates/base.html templates/partials/ web/tests/test_pages.py
git commit -m "feat(web): full base.html with meta/OG blocks, JSON-LD, GA, page chrome"
```

---

### Task 4: Port the pure CSS design system into static

Copies all 27 CSS files verbatim from the SPA into `static/css/`. `base.html` already links `global.css` + `effects.css`; component/page sheets are copied now (cheap) and linked per-page in later plans via `{% block extra_css %}`.

**Files:**
- Create: `static/css/*.css` (27 files, verbatim copies)
- Create: `static/img/favicon.svg`, `static/img/og-image.jpg` (copied from the SPA `public/`)
- Reference (read/copy): `../www_fortkentcinema_com/src/**/*.css`, `../www_fortkentcinema_com/public/favicon.svg`, `../www_fortkentcinema_com/public/og-image.jpg`
- Modify: `web/tests/test_pages.py`

**Interfaces:**
- Produces: static assets resolvable via `{% static 'css/global.css' %}`, `{% static 'css/effects.css' %}`, `{% static 'img/favicon.svg' %}`; the full set of component/page CSS files present in `static/css/` for later `{% block extra_css %}` links.

- [ ] **Step 1: Write the failing test**

Add to `web/tests/test_pages.py`:

```python
from django.contrib.staticfiles.finders import find


class StaticAssetsTests(TestCase):
    def test_core_css_present(self):
        for name in ("css/variables.css", "css/global.css", "css/effects.css"):
            self.assertIsNotNone(find(name), f"missing static asset: {name}")

    def test_component_css_present(self):
        # Representative sample of the ported component/page sheets.
        for name in ("css/Hero.css", "css/Nav.css", "css/Footer.css", "css/NowShowing.css"):
            self.assertIsNotNone(find(name), f"missing static asset: {name}")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python manage.py test web`
Expected: FAIL — `AssertionError: missing static asset: css/variables.css`.

- [ ] **Step 3: Copy the CSS files verbatim**

Copy every `.css` file from the SPA into `static/css/`, flattening to basenames. Run from the Django repo root:

```bash
mkdir -p static/css static/img
SPA=../www_fortkentcinema_com
cp "$SPA"/src/styles/variables.css static/css/variables.css
cp "$SPA"/src/styles/global.css static/css/global.css
cp "$SPA"/src/styles/effects.css static/css/effects.css
# Component + page sheets (basename-flattened):
find "$SPA/src/components" "$SPA/src/pages" -name '*.css' -exec cp {} static/css/ \;
# Favicon + OG image:
cp "$SPA"/public/favicon.svg static/img/favicon.svg
cp "$SPA"/public/og-image.jpg static/img/og-image.jpg
ls static/css | wc -l   # expect 27
```

**Do not edit any copied file.** `global.css` keeps its top `@import url('https://fonts.googleapis.com/...')` and `@import './variables.css';` — both resolve correctly as siblings in `static/css/`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python manage.py test web`
Expected: PASS.

- [ ] **Step 5: Verify visually in the dev server (manual smoke check)**

Run: `python manage.py runserver` and open `http://127.0.0.1:8000/`. Expect the dark Art Deco background (`#0a0a0e`), champagne-gold text, film-grain overlay, and Google Fonts (Poiret One / Playfair Display / Cormorant Garamond) applied to the placeholder `<h1>`. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add static/css/ static/img/
git commit -m "feat(web): port pure-CSS design system + favicon/og image into static"
```

---

### Task 5: Effects build pipeline (ambient dust + scroll reveal)

Sets up a Vite build under `frontend/` that compiles the framework-agnostic effects `core/` (copied verbatim) plus vanilla `initAmbientDust` / `initScrollReveal` and a `main.js` boot into `static/js/effects.js`. Ports the `core/` unit tests to Vitest. Cursor-bulbs / neon / card-spotlight init modules are **out of scope** here — they attach to hero/cards introduced in the Home plan.

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.js`, `frontend/vitest.setup.js`
- Create: `frontend/effects/core/{animationLoop,pointer,scrollProgress,motionPrefs}.js` (verbatim copies)
- Create: `frontend/effects/init/{ambientDust,scrollReveal}.js`, `frontend/effects/main.js`
- Create: `frontend/effects/__tests__/{scrollProgress,motionPrefs,scrollReveal}.test.js`
- Reference (read/copy): `../www_fortkentcinema_com/src/effects/core/*.js` and their `__tests__`, `../www_fortkentcinema_com/src/effects/hooks/{useScrollReveal,useAmbientDust}.js`
- Build output: `static/js/effects.js` (committed, since deploy runs `collectstatic` not a JS build)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `static/js/effects.js` (ES module) referenced by `base.html`; `initAmbientDust(root=document)` (attaches to `[data-ambient-dust]`), `initScrollReveal(root=document)` (attaches to `[data-reveal]`), booted on `DOMContentLoaded` and re-armed on `htmx:afterSwap`.

- [ ] **Step 1: Create the frontend build package**

Create `frontend/package.json`:

```json
{
  "name": "fortkentcinema-effects",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "d3-timer": "^3.0.1"
  },
  "devDependencies": {
    "vite": "^7.2.4",
    "vitest": "^2.1.9",
    "jsdom": "^25.0.1"
  }
}
```

Create `frontend/vite.config.js` — build a single self-contained IIFE/ES bundle into `../static/js/`:

```js
import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  build: {
    outDir: resolve(import.meta.dirname, '../static/js'),
    emptyOutDir: false,
    lib: {
      entry: resolve(import.meta.dirname, 'effects/main.js'),
      formats: ['es'],
      fileName: () => 'effects.js',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.js'],
  },
});
```

Create `frontend/vitest.setup.js`:

```js
// Provide a deterministic rAF in jsdom for scrollProgress tests.
if (typeof globalThis.requestAnimationFrame !== 'function') {
  globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
  globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
}
```

Run: `cd frontend && npm install`
Expected: dependencies install cleanly.

- [ ] **Step 2: Copy the core modules verbatim + port their tests (write failing tests)**

Copy the four core files unchanged:

```bash
mkdir -p frontend/effects/core frontend/effects/init frontend/effects/__tests__
SPA=../www_fortkentcinema_com
cp "$SPA"/src/effects/core/{animationLoop,pointer,scrollProgress,motionPrefs}.js frontend/effects/core/
```

Copy the existing core tests the SPA already ships (they import from `../core/*`), adjusting only import paths if needed:

```bash
cp "$SPA"/src/effects/core/__tests__/scrollProgress.test.js frontend/effects/__tests__/scrollProgress.test.js
cp "$SPA"/src/effects/core/__tests__/motionPrefs.test.js frontend/effects/__tests__/motionPrefs.test.js
```

Edit the two copied test files so their imports point at `../core/<name>` (e.g. `import { onScrollProgress } from '../core/scrollProgress';`).

- [ ] **Step 3: Run the ported core tests to verify they fail (path not yet resolved) then pass after fixups**

Run: `cd frontend && npm test`
Expected: after correcting import paths, the core tests PASS (they exercise the verbatim-copied modules). If a test depends on a browser API absent in jsdom, confirm `vitest.setup.js` covers it. Do not modify `core/*` logic.

- [ ] **Step 4: Write the failing test for `initScrollReveal`**

Create `frontend/effects/__tests__/scrollReveal.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { initScrollReveal } from '../init/scrollReveal.js';

describe('initScrollReveal', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div data-reveal id="t">hi</div>';
  });

  it('marks elements revealed immediately under reduced motion', () => {
    // Force the "static" tier: no matchMedia => getMotionTier() === 'static'
    vi.stubGlobal('matchMedia', undefined);
    initScrollReveal(document);
    const el = document.getElementById('t');
    expect(el.classList.contains('fx-reveal')).toBe(true);
    expect(el.classList.contains('fx-revealed')).toBe(true);
  });
});
```

Run: `cd frontend && npm test`
Expected: FAIL — cannot resolve `../init/scrollReveal.js`.

- [ ] **Step 5: Write the init modules (vanilla ports of the hooks)**

Create `frontend/effects/init/scrollReveal.js` (port of `useScrollReveal`, DOM-scan form):

```js
import { onScrollProgress } from '../core/scrollProgress.js';
import { getMotionTier } from '../core/motionPrefs.js';

const FADE_SPAN = 0.3;

function reveal(node) {
  try {
    if (getMotionTier() === 'static') {
      node.classList.add('fx-reveal', 'fx-revealed');
      return;
    }
    node.classList.add('fx-reveal');
    let unsubscribe = onScrollProgress(node, (progress) => {
      node.style.setProperty('--fx-draw', String(progress));
      node.style.setProperty('--fx-fade', String(Math.min(progress / FADE_SPAN, 1)));
      if (progress >= 1) {
        node.classList.add('fx-revealed');
        if (unsubscribe) { unsubscribe(); unsubscribe = null; }
      }
    });
  } catch (err) {
    console.error('[effects] scroll reveal disabled:', err);
    node.classList.add('fx-reveal', 'fx-revealed');
  }
}

export function initScrollReveal(root = document) {
  root.querySelectorAll('[data-reveal]').forEach((node) => {
    if (node.dataset.revealInit) return; // idempotent across HTMX swaps
    node.dataset.revealInit = '1';
    reveal(node);
  });
}
```

Create `frontend/effects/init/ambientDust.js` (port of `useAmbientDust`, canvas-scan form):

```js
import { onTick } from '../core/animationLoop.js';
import { onPointer } from '../core/pointer.js';
import { getMotionTier } from '../core/motionPrefs.js';

const REPEL_RADIUS = 70;
const MIN_FADE = 0.35;

function start(canvas) {
  const tier = getMotionTier();
  if (tier === 'static') return;
  try {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let width = 0;
    let height = 0;
    function resize() {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    }
    resize();
    const count = window.innerWidth < 700 ? 25 : 50;
    const motes = Array.from({ length: count }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: Math.random() * 1.6 + 0.4,
      vx: (Math.random() - 0.5) * 0.15,
      vy: -(Math.random() * 0.2 + 0.05),
      a: Math.random() * 0.4 + 0.1,
    }));
    const cursor = { sx: -9999, sy: -9999 };
    if (tier === 'full') {
      onPointer((p) => { cursor.sx = p.sx; cursor.sy = p.sy; });
    }
    onTick(() => {
      ctx.clearRect(0, 0, width, height);
      const fade = Math.max(MIN_FADE, 1 - window.scrollY / (height * 2));
      motes.forEach((m) => {
        const dx = m.x - cursor.sx;
        const dy = m.y - cursor.sy;
        const dist = Math.hypot(dx, dy);
        if (dist < REPEL_RADIUS && dist > 0) {
          m.x += (dx / dist) * 1.1;
          m.y += (dy / dist) * 1.1;
        }
        m.x += m.vx;
        m.y += m.vy;
        if (m.y < -5) { m.y = height + 5; m.x = Math.random() * width; }
        if (m.x < -5) m.x = width + 5;
        if (m.x > width + 5) m.x = -5;
        ctx.beginPath();
        ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(201, 168, 76, ${m.a * fade})`;
        ctx.fill();
      });
    });
    window.addEventListener('resize', resize);
  } catch (err) {
    console.error('[effects] ambient dust disabled:', err);
  }
}

export function initAmbientDust(root = document) {
  const canvas = root.querySelector('[data-ambient-dust]');
  if (!canvas || canvas.dataset.dustInit) return;
  canvas.dataset.dustInit = '1';
  start(canvas);
}
```

- [ ] **Step 6: Run the init test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS (core tests + `scrollReveal` test).

- [ ] **Step 7: Write the boot entry point**

Create `frontend/effects/main.js`:

```js
import { initAmbientDust } from './init/ambientDust.js';
import { initScrollReveal } from './init/scrollReveal.js';

function boot() {
  initAmbientDust(document);
  initScrollReveal(document);
}

if (document.readyState !== 'loading') {
  boot();
} else {
  document.addEventListener('DOMContentLoaded', boot);
}

// Re-arm scroll reveals on HTMX-swapped content (used from later plans).
document.body.addEventListener('htmx:afterSwap', (e) => initScrollReveal(e.target));
```

- [ ] **Step 8: Build the bundle**

Run: `cd frontend && npm run build`
Expected: writes `static/js/effects.js`. Verify: `test -f ../static/js/effects.js && echo OK`.

- [ ] **Step 9: Commit**

```bash
cd ..
git add frontend/ static/js/effects.js
git commit -m "feat(effects): vite build for ambient dust + scroll reveal vanilla bundle"
```

---

### Task 6: Remove Tailwind/Flowbite tooling

Deletes the unused Tailwind/Flowbite scaffolding from the Django project's root `package.json` (zero `.html` referenced them). The effects build lives in `frontend/` and is unaffected.

**Files:**
- Modify or delete: `package.json`, `package-lock.json` (repo root)
- Delete if present: `tailwind.config.*`, `postcss.config.*`

**Interfaces:**
- Produces: no Tailwind/Flowbite/PostCSS dependencies anywhere in the repo.

- [ ] **Step 1: Confirm nothing references Tailwind/Flowbite**

Run: `grep -rin "tailwind\|flowbite\|@apply" --include=*.html --include=*.css --include=*.py . ; echo "exit: $?"`
Expected: no matches (grep exit 1). If matches appear, stop and report — the assumption that they're unused is wrong.

- [ ] **Step 2: Remove the tooling**

The root `package.json` exists only for Tailwind/Flowbite scaffolding. Delete it and its lockfile and any PostCSS/Tailwind configs:

```bash
rm -f package.json package-lock.json tailwind.config.js tailwind.config.cjs postcss.config.js postcss.config.cjs
```

- [ ] **Step 3: Verify the effects build is independent**

Run: `cd frontend && npm run build && test -f ../static/js/effects.js && echo OK`
Expected: `OK` — the `frontend/` build has its own `package.json` and does not depend on the deleted root one.

- [ ] **Step 4: Commit**

```bash
cd ..
git add -A
git commit -m "chore: remove unused Tailwind/Flowbite tooling"
```

---

### Task 7: Deploy-ready static settings (WhiteNoise + ALLOWED_HOSTS)

Serves collected static files in production via WhiteNoise and ensures `www.fortkentcinema.com` is an allowed host. Static/media S3 (`django-storages`) remains available behind `ENABLE_CDN` — unchanged.

**Files:**
- Modify: `fortkentcinema/settings.py` (MIDDLEWARE, STORAGES, ALLOWED_HOSTS note)
- Modify: `requirements.txt` (add whitenoise)
- Create: `web/tests/test_settings.py`

**Interfaces:**
- Produces: WhiteNoise middleware active; `collectstatic` produces a servable `staticfiles/` tree.

- [ ] **Step 1: Write the failing test**

Create `web/tests/test_settings.py`:

```python
from django.conf import settings
from django.test import SimpleTestCase


class StaticServingSettingsTests(SimpleTestCase):
    def test_whitenoise_middleware_present(self):
        self.assertIn(
            "whitenoise.middleware.WhiteNoiseMiddleware", settings.MIDDLEWARE
        )

    def test_whitenoise_after_security_middleware(self):
        mw = settings.MIDDLEWARE
        self.assertLess(
            mw.index("django.middleware.security.SecurityMiddleware"),
            mw.index("whitenoise.middleware.WhiteNoiseMiddleware"),
        )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python manage.py test web.tests.test_settings`
Expected: FAIL — WhiteNoise not in MIDDLEWARE.

- [ ] **Step 3: Add WhiteNoise to requirements and install**

Add to `requirements.txt` (under a "Static serving" comment):

```
# Static serving
whitenoise==6.7.0
```

Run: `pip install whitenoise==6.7.0`

- [ ] **Step 4: Wire WhiteNoise in settings**

In `fortkentcinema/settings.py`, insert the WhiteNoise middleware immediately **after** `SecurityMiddleware`:

```python
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

Add a `STORAGES` block for compressed, cache-busted static (place after `STATIC_ROOT`), leaving S3 to `ENABLE_CDN` as before:

```python
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

Note: `ALLOWED_HOSTS` is env-driven via `config("ALLOWED_HOSTS", cast=Csv())` — ensure the deploy `.env` includes `www.fortkentcinema.com,fortkentcinema.com` (documented for the cutover plan; no code change here).

- [ ] **Step 5: Run the test to verify it passes**

Run: `python manage.py test web.tests.test_settings`
Expected: PASS.

- [ ] **Step 6: Verify collectstatic works end-to-end**

Run: `python manage.py collectstatic --noinput`
Expected: collects the CSS/JS/img into `staticfiles/` with no errors (hashed manifest names).

- [ ] **Step 7: Run the full suite**

Run: `python manage.py test`
Expected: all Django tests pass (web + existing blog API tests untouched).

- [ ] **Step 8: Commit**

```bash
git add fortkentcinema/settings.py requirements.txt web/tests/test_settings.py
git commit -m "feat(deploy): serve static via WhiteNoise with manifest storage"
```

---

## Self-Review

**Spec coverage (against `2026-07-02-django-migration-design.md`):**
- Architecture & layout (`web` app, project `templates/`, `base.html`, static) → Tasks 1, 3, 4.
- `site_config` context processor + ported `siteConfig.json`/`membership.json` → Task 2.
- SEO/meta blocks + `MovieTheater` JSON-LD + GA → Task 3.
- Pure-CSS verbatim port; fonts via `global.css` `@import` → Task 4.
- Effects vanilla-JS bundle (globally-present: ambient dust, scroll reveal), motion-tier guards, HTMX re-arm hook, ported core Vitest tests → Task 5.
- Remove Tailwind/Flowbite → Task 6.
- Deployment static serving (WhiteNoise; S3 remains optional) + ALLOWED_HOSTS → Task 7.
- **Deferred by design (later plans):** leprinceos service + Home (Plan 2); blog pages (Plan 3); classics/membership/rentals/about + calendar HTMX (Plan 4); sitemap/robots + Selenium E2E + cutover (Plan 5). Cursor-bulbs/neon/card-spotlight init modules land in Plan 2 with their target elements.

**Placeholder scan:** No "TBD/TODO" left as work items. The two intentional fill-ins — `MEMBERSHIP` transcription (Task 2, Step 3) and placeholder nav/footer partials (Task 3) — have explicit instructions and defined follow-up plans.

**Type/name consistency:** `initScrollReveal(root)` / `initAmbientDust(root)` signatures match between `main.js` (Task 5, Step 7), the init modules (Step 5), and the test (Step 4). `base.html` block names (`meta/title/description/og_*/extra_css/extra_head/content/extra_js`) are consistent across Tasks 1 and 3. `data-ambient-dust` / `data-reveal` attributes match between `base.html` (Task 3) and the init scanners (Task 5). `SITE_CONFIG`/`MEMBERSHIP` names consistent across Task 2. `find("css/…")` names in Task 4's test match the flattened basenames produced by the copy step.
</content>
