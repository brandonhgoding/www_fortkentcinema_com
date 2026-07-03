# Design: Migrate Fort Kent Cinema frontend from React SPA to server-rendered Django

**Date:** 2026-07-02
**Status:** Approved (design), pending implementation plan
**Target repo:** `api_fortkentcinema_com` (the existing Django project behind `api.fortkentcinema.com`)
**Source repo:** `www_fortkentcinema_com` (React 19 + Vite SPA, to be retired)

## Problem

The live site (`www.fortkentcinema.com`) is a client-rendered React SPA. Social/link-preview
crawlers (Facebook, iMessage, Slack, LinkedIn, Twitter/X) do not execute JavaScript and do not
wait for the SPA's client-side `fetch` calls, so they only ever read the static default
`<meta>`/`og:` tags in `index.html`. Sharing a blog post shows the site's default image and
description instead of the post's own. `react-helmet-async` sets correct per-page tags, but
too late — in the browser, after the crawler has already left.

The fix is to render HTML (and its meta tags) on the server. Rather than bolt a workaround
(prerender service / Lambda@Edge) onto the SPA, we migrate the frontend into the Django project
that already owns the blog data, rendering every page server-side. This solves link previews for
**every** page as a side effect of the architecture, and adds real SEO (sitemap, JSON-LD) the SPA
never had.

## Goals

- The public site looks **pixel-identical** to today, including motion/ambient visual effects.
- Correct per-page `<title>`/`<meta>`/`og:` tags in the initial server response, on every route.
- No React. No client-side SPA routing. Server-rendered Django templates.
- Consolidate the site into the existing `api_fortkentcinema_com` Django project.

## Non-Goals

- No visual redesign. "Exactly the same" is the acceptance bar.
- No change to the multi-tenant leprinceos (cinema_sass) product; it stays an external API we consume.
- No migration of blog data — it already lives natively in this Django project's `blog` app.
- No pure-static hosting (S3/CloudFront alone) — server rendering requires a running server.

## Decisions (from brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Backend ownership | User owns both leprinceos (cinema_sass) and the blog backend |
| 2 | Where the work lives | Migrate into existing `api_fortkentcinema_com` Django project |
| 3 | Cinema data sourcing | **Approach A**: server-side fetch of leprinceos API + short-TTL cache w/ stale-fallback |
| 4 | Styling | Port the 27 pure-CSS files + `variables.css` verbatim into Django static |
| 5 | Tailwind/Flowbite | **Remove** them — everything is pure CSS (they are unused scaffolding today) |
| 6 | Visual effects | Port as a vanilla-JS bundle: keep framework-agnostic `core/`, rewrite hook wrappers |
| 7 | Interactivity | HTMX (server-driven swaps) + Alpine (tiny client state) |
| 8 | Views | Class-based views wherever a generic view fits |
| 9 | Testing | Django built-in `unittest`; Selenium for E2E; TDD throughout |
| 10 | Cutover | Big-bang: build all pages first, verify parity in staging, single DNS flip |

## Architecture & Project Layout

The project stops being "just an API" and becomes the whole `fortkentcinema.com` stack. A new
`web` app renders the cinema/static pages; the existing `blog` app keeps its DRF API **and** gains
template-rendering views.

```
api_fortkentcinema_com/
├── fortkentcinema/
│   ├── settings.py             # + 'web', templates DIRS, cache, LEPRINCEOS_BASE_URL; - tailwind
│   ├── urls.py                 # + web.urls at "/", + blog template urls, keep "api/" (DRF)
│   └── context_processors.py   # site_config (cinema info, hours, nav, social)
├── blog/                       # existing DRF API + NEW ListView/DetailView template views
├── web/                        # NEW app
│   ├── views.py                # home, membership, classics, rentals, about (CBVs)
│   ├── urls.py
│   ├── services/
│   │   └── leprinceos.py       # server-side port of the SPA's api.js (cache + stale fallback)
│   ├── constants.py            # ported siteConfig.json + membership.json
│   └── templates/web/
├── templates/
│   ├── base.html               # head meta/OG/JSON-LD, curtains, vignette, nav, footer, skip-link
│   └── partials/               # nav, footer, movie_card, coming_soon, calendar, cta_*, blog_card
├── static/
│   ├── css/                    # 27 ported CSS files + variables.css, VERBATIM
│   ├── js/                     # built effects bundle + htmx/alpine glue (build output)
│   ├── fonts/  img/
├── frontend/                   # Vite/esbuild SOURCE for effects JS only → builds into static/js/
│   ├── effects/core/           # copied verbatim from SPA (pointer, animationLoop, scrollProgress, motionPrefs)
│   ├── effects/init*.js        # vanilla rewrites of the React hooks
│   └── main.js                 # boot entry point
└── docs/superpowers/specs/     # this document
```

**Routes** (`web.urls` + blog template urls, mounted at `/`), matching the SPA exactly:
`/`, `/blog`, `/blog/<slug>`, `/membership`, `/classics`, `/rentals`, `/about`.
`api/` stays mounted for the existing DRF endpoints — nothing that consumes them breaks.

**Rendering model:** each route is a class-based view that gathers data (model queries for blog;
cached leprinceos calls for cinema data; context processor for site config) and renders a template
that `{% extends "base.html" %}`. `base.html` carries the per-page meta block.

## Component → Template Mapping

**Pages** (view + template, each extends `base.html`):

| React | Django view | Kind | Template | Data source |
|---|---|---|---|---|
| `HomePage` | `web.views.HomeView` | `TemplateView` | `web/home.html` | leprinceos (now/coming) + config |
| `BlogListPage` | `blog.views.PostListView` | `ListView` | `blog/post_list.html` | `BlogPost` queryset (paginated) |
| `BlogDetailPage` | `blog.views.PostDetailView` | `DetailView` | `blog/post_detail.html` | `BlogPost` by slug |
| `MembershipPage` | `web.views.MembershipView` | `TemplateView` | `web/membership.html` | `membership` constants |
| `ClassicMoviePage` | `web.views.ClassicsView` | `TemplateView` | `web/classics.html` | leprinceos `kind=CLASSIC` |
| `PrivateRentalsPage` | `web.views.RentalsView` | `TemplateView` | `web/rentals.html` | static |
| `AboutPage` | `web.views.AboutView` | `TemplateView` | `web/about.html` | static |

**Reusable partials** (`templates/partials/`):

| React | Partial | Notes |
|---|---|---|
| `Nav` | `partials/nav.html` | Alpine for mobile toggle; hash links on home, routes elsewhere |
| `Footer` | `partials/footer.html` | |
| `Hero` | `partials/hero.html` | |
| `MovieCard` | `partials/movie_card.html` | `data-spotlight` |
| `MovieScheduleCard` | `partials/movie_schedule_card.html` | |
| `ComingSoon` (+ calendar) | `partials/coming_soon.html`, `partials/calendar_month.html` | calendar is an HTMX swap target |
| `Membership` (Tiers/Benefits) | `partials/membership_tiers.html`, `partials/membership_benefits.html` | |
| `BlogCard`/`BlogPost` | `partials/blog_card.html` | |
| `ClassicMovieCTA`/`GiftCardCTA`/`OpenMicCTA` | `partials/cta_classic.html`, `cta_giftcard.html`, `cta_openmic.html` | |
| `SectionDivider`/`AmbientDust` | markup in `base.html`; effects JS attaches | `data-section-divider`, `data-ambient-dust` |

**HTMX fragment endpoints** (return HTML fragments when `HX-Request`; full page otherwise):

- `GET /blog/page/<n>` → more `blog_card` rows (infinite scroll; replaces IntersectionObserver pagination)
- `GET /calendar/<year>/<month>` → `calendar_month.html` fragment (month navigation)
- Showtime date filtering → **Alpine only**, client-side show/hide of data already in the DOM
  (mirrors the current `useMemo` behavior; no round-trip)

`web` owns cinema/static pages; the existing `blog` app gains the two template views alongside its
DRF viewsets.

## Effects JS Porting Strategy

Goal: identical motion/ambient polish with zero React. The SPA's `effects/` tree is already
layered into framework-agnostic `core/` + React hook wrappers, which makes this mostly mechanical.

**Keep verbatim** (copy into `frontend/effects/core/`): `motionPrefs.js`, `pointer.js`,
`animationLoop.js`, `scrollProgress.js` — plain modules, no React.

**Rewrite hook wrappers as vanilla initializers** — each `init<Effect>(root)` finds targets by
`data-` attribute and wires the same core logic:

| React hook/component | Vanilla module | Attaches to |
|---|---|---|
| `useAmbientDust` / `AmbientDust` | `initAmbientDust()` | `[data-ambient-dust]` canvas in `base.html` |
| `useNeonPowerOn` | `initNeonPowerOn()` | `[data-neon]` |
| `useCursorBulbs` | `initCursorBulbs()` | `[data-cursor-bulbs]` |
| `useCardSpotlight` | `initCardSpotlight()` | `[data-spotlight]` |
| `useScrollReveal` | `initScrollReveal()` | `[data-reveal]` (IntersectionObserver) |
| `SectionDivider` | `initSectionDividers()` | `[data-section-divider]` |

**Entry point** `frontend/main.js`:

```js
import { prefersReducedMotion } from './effects/core/motionPrefs.js';
// ...init imports
function boot() {
  if (prefersReducedMotion()) return;            // same guard as the SPA
  initAmbientDust(); initNeonPowerOn(); initCursorBulbs();
  initCardSpotlight(); initScrollReveal(); initSectionDividers();
}
document.addEventListener('DOMContentLoaded', boot);
document.body.addEventListener('htmx:afterSwap', (e) => initScrollReveal(e.target)); // re-arm on swaps
```

**Build:** Vite (or esbuild) builds `frontend/main.js` → `static/js/effects.[hash].js`, referenced
in `base.html` via `django-vite` or a small manifest lookup. `prefers-reduced-motion` honored
exactly as today.

**Attribute placement:** the SPA applies effects via hooks on specific elements; each `data-`
attribute is ported to the corresponding partial by cross-referencing the component's JSX (e.g.
`MovieCard`'s spotlight → `data-spotlight` on `movie_card.html`).

## Data Flow & the leprinceos Service Layer

`web/services/leprinceos.py` is a server-side port of the SPA's `src/services/api.js` — same
endpoints, same transforms — swapping browser `fetch` for Python `requests` and adding caching.

**Functions ported 1:1** (same output shapes the templates expect): `get_now_showing()`,
`get_coming_soon()`, `get_calendar_month(year, month)`, `get_classic_movie_night()`,
`get_movie_by_id(id)`, `get_showtimes(engagement_id)`.

**Timezone:** use `zoneinfo.ZoneInfo("America/New_York")`. Parse UTC `starts_at`, convert, format
display times (`"6:00 PM"`) and `YYYY-MM-DD` date keys. Same group-by-local-date logic as the SPA.

**Caching (Approach A):**

```python
def _get(path, ttl=180):
    key = f"lpos:{path}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        data = requests.get(BASE_URL + path, timeout=4).json()
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        cache.set(key, results, ttl)
        cache.set(f"{key}:stale", results, None)   # last-good, no expiry
        return results
    except Exception:
        return cache.get(f"{key}:stale", [])        # serve stale on failure
```

- Fresh TTL ~3 min; **stale-fallback** with no expiry — a leprinceos outage degrades to
  last-known data, never a broken page.
- `timeout=4` so a slow upstream can't hang a render.
- Cache backend: **LocMemCache** to start (zero infra); swap to Redis later via a settings change
  if scaled to multiple workers — no code change.

**Config:** `LEPRINCEOS_BASE_URL` in settings via `python-decouple` (already used), so
local/staging/prod can point wherever.

**Static config:** `siteConfig.json` and `membership.json` move into `web/constants.py`
(or JSON loaded once at startup). Exposed to all templates via the `site_config` context processor,
so `base.html` (nav, footer, hours, address) always has them.

**Blog data:** no service layer — `ListView`/`DetailView` query `BlogPost` directly. `header_image`
is an S3 `ImageField`, so `og:image` gets a real absolute URL for free.

## SEO & Meta Tags

Server-rendered, so meta tags are in the initial HTML — no JS, no Helmet, no edge workaround.

**`base.html` head block** — site-wide defaults, each overridable per page:

```django
{% block meta %}
  <title>{% block title %}Fort Kent Cinema{% endblock %}</title>
  <meta name="description" content="{% block description %}Maine's Northernmost Picture Show{% endblock %}">
  <meta property="og:title" content="{% block og_title %}{{ self.title }}{% endblock %}">
  <meta property="og:description" content="{% block og_description %}{{ self.description }}{% endblock %}">
  <meta property="og:image" content="{% block og_image %}{% static 'img/default-og.jpg' %}{% endblock %}">
  <meta property="og:url" content="{{ request.build_absolute_uri }}">
  <meta property="og:type" content="{% block og_type %}website{% endblock %}">
  <link rel="canonical" href="{{ request.build_absolute_uri }}">
{% endblock %}
```

**Blog detail** overrides with real per-post data (finally correct on shares):

```django
{% block og_image %}{{ post.header_image.url }}{% endblock %}
{% block og_description %}{{ post.subtitle }}{% endblock %}
{% block og_type %}article{% endblock %}
```

Same pattern for every page (posters for classics/movies; tailored copy for membership/rentals/
about). All absolute URLs via `request.build_absolute_uri` / `ImageField.url`.

**Structured data:** port the `schema.org` `MovieTheater` JSON-LD from the SPA's `index.html` into
`base.html`, sourced from `site_config` (address, hours, phone) — on every page, accurate.

**Sitemap + robots:** add `django.contrib.sitemaps` — static sitemap for fixed pages +
`BlogPostSitemap` from the queryset (auto-includes new posts). Wire `sitemap.xml` and `robots.txt`.

## Testing Strategy

Django built-in `unittest` (`manage.py test`) + Selenium E2E. **TDD throughout** (red → green →
refactor): every view/service/fragment and every E2E flow starts as a failing test.

**Django view tests** (`django.test.TestCase`):

- Each CBV returns `200` and uses the expected template (`assertTemplateUsed`).
- `ListView` blog pagination: page size, `-post_date` ordering, pagination context.
- `DetailView`: slug resolves the right post; unknown slug → `404`.
- HTMX fragment views: `HX-Request` header → fragment template; without → full page. Calendar
  month view returns the correct month.
- `home`/`classics`: leprinceos service **mocked**; assert context shape (no live network in tests).

**leprinceos service tests** (mocked `requests`):

- Transform correctness (highest value): UTC → `America/New_York`, date grouping, DRF `results`
  unwrap, runtime formatting, Coming Soon dedup.
- Cache behavior: fresh hit skips network; expiry re-fetches; **failure serves stale last-good**;
  timeout does not propagate.

**Meta/SEO tests:**

- Each page renders `og:title`/`og:description`/`og:image`; blog detail carries post-specific
  image + description + `og:type=article` — directly guards the original bug.
- `sitemap.xml` includes published posts; `robots.txt` serves.

**Effects (Vitest):**

- Port `effects/core/__tests__/*` (pointer, animationLoop, scrollProgress, motionPrefs) against the
  copied core modules.
- `prefers-reduced-motion` guard: `boot()` no-ops when reduced motion is set.

**Selenium E2E** (`StaticLiveServerTestCase` + WebDriver) — runtime-only behaviors:

- Effects boot (canvas present / reveal classes applied); a reduced-motion run asserts no-op.
- HTMX infinite scroll appends posts; calendar month swap updates the grid.
- Alpine mobile menu opens/closes.
- Blog list → detail navigation; correct meta present in detail page source.

**Existing API tests:** the `blog` DRF tests keep passing untouched — the API surface is unchanged;
we only add template views.

**Parity gate (pre-cutover):** manual page-by-page visual diff against the live SPA in staging —
the human check that "exactly the same" holds before DNS flips.

## Cutover & Deployment Plan

**Strategy:** big-bang, build-all-first. All work on a branch in `api_fortkentcinema_com`; nothing
user-facing changes until the final DNS flip.

**Build order** (each page TDD'd + parity-checked in staging):

1. Scaffold: `web` app, `base.html`, ported CSS/fonts to `static/`, context processor, remove
   Tailwind/Flowbite, Vite effects build.
2. Home (Hero, NowShowing, ComingSoon, Membership, CTAs) — exercises leprinceos service + effects.
3. Blog list + detail (native models; **proves the OG-tag fix**).
4. Classics, Membership, Rentals, About.
5. HTMX fragments (infinite scroll, calendar), sitemap/robots.
6. Full Selenium E2E pass + manual visual parity sweep vs. live SPA.

**Deployment shape:**

- Full Django needs a running server → pure-static S3/CloudFront is off the table for the site.
  Run **Django (gunicorn/uvicorn) behind nginx**, deployed via the existing **`ansible/`** setup.
  EC2 (current) is the natural home.
- **Static files:** `collectstatic` → **WhiteNoise** (start here, one dependency) or **S3** via the
  `django-storages`/`boto3` already in `requirements.txt` (config swap, no code change).
- **Media:** blog images already on S3 — unchanged.
- **Domains:** one Django project serves both `www.fortkentcinema.com` (site) and
  `api.fortkentcinema.com` (existing DRF). Add `www` to `ALLOWED_HOSTS`; `api/` stays mounted.
  `og:url`/canonical use the `www` host.

**Cutover & rollback:**

- Deploy to staging; run full test + parity gate.
- Flip `www.fortkentcinema.com` DNS/origin from the React host to the Django server.
- **Rollback:** keep the React build deployable; flip DNS back on regression. Zero data risk —
  blog data already lives in this DB; leprinceos is read-only.
- **After a stable window:** archive the `www_fortkentcinema_com` React repo (README pointer to the
  new home).

## Open Questions / Follow-ups (non-blocking)

- Confirm `blog.content` format (HTML vs Markdown) to choose the correct template rendering/escaping
  (`|safe` vs a Markdown filter) — determined during blog-page implementation.
- Decide WhiteNoise vs S3 for static at deploy time (default: WhiteNoise).
- Redis vs LocMemCache depends on worker count at deploy time (default: LocMemCache).
</content>
</invoke>
