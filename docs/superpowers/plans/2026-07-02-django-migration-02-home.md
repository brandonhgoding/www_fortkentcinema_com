# Django Migration — Plan 2: Home Page + leprinceos Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder home page with the real server-rendered homepage — Hero, Now Showing, Coming Soon (grid), the promotional CTAs, and the Blog teaser — backed by a cached server-side port of the SPA's leprinceos data layer, with the Hero/card visual effects and Alpine-driven interactivity (date navigation, trailer modals) preserving the SPA's behavior.

**Architecture:** A `web/services/leprinceos.py` module ports `src/services/api.js` server-side (Python `requests` + `zoneinfo`, short-TTL cache with stale fallback). `web/services/showtimes.py` ports the `showtimeDates` date helpers. `HomeView` (a `TemplateView`) gathers `now_showing` + `coming_soon` and renders `web/home.html`, which composes section partials. Client-side motion effects gain three more vanilla init modules (neon power-on, cursor bulbs, card spotlight); interactivity that was React state (date nav, trailer modal, phone/desktop split) becomes Alpine + responsive CSS with all data rendered server-side.

**Tech Stack:** Django 5.2.3 class-based views + templates, `requests`, `zoneinfo`, Django cache (LocMem), Alpine.js (client interactivity), the existing Vite effects bundle. Tests: Django `unittest` (mocked `requests`), Vitest for effects.

## Global Constraints

- Target repo: `api_fortkentcinema_com`, branch `feat/django-frontend-migration` (continues from Plan 1).
- Django 5.2.3; existing `api/` DRF surface untouched. Activate `.venv` (`source .venv/bin/activate`) for all Django commands; `.env` (gitignored, `DEBUG=True`) auto-loads.
- leprinceos API base: `https://www.leprinceos.com/api/v1`. Add `LEPRINCEOS_BASE_URL` to settings via `python-decouple` `config(...)` with that default.
- Cinema timezone: `America/New_York` (use `zoneinfo.ZoneInfo`). `TIME_ZONE`/`USE_TZ=True` already set.
- Data shapes MUST match the SPA's `api.js` output exactly (the templates were designed around them). Documented per task.
- Markup is ported to preserve **every CSS class name and DOM structure** from the source React component — the acceptance bar is pixel-identical rendering. CSS is already in `static/css/` from Plan 1; templates link the matching sheet via `{% block extra_css %}`.
- Effects honor motion tiers via `getMotionTier()` (already copied verbatim). New init modules are faithful vanilla ports of the SPA hooks.
- Interactivity: **Alpine.js** for client state (date nav, trailer modal, view toggles); no React. All list/showtime data is server-rendered into the DOM; Alpine only shows/hides/toggles.
- **Home composition order** (from `src/App.jsx` `HomePage`): Hero → OrnamentDivider → ClassicMovieCTA → OrnamentDivider → NowShowing → OrnamentDivider → OpenMicCTA → OrnamentDivider → ComingSoon → OrnamentDivider → GiftCardCTA → OrnamentDivider → Blog-teaser. On phones (`max-width: 600px`) only NowShowing + ComingSoon + footer show; Hero, all CTAs, and Blog-teaser are hidden. Since the server can't detect viewport, render the full DOM and control phone-stripping with CSS `@media (max-width: 600px)` (the SPA hid these via JS; we hide via CSS — visually identical).
- **Membership is NOT on the home page** (it's the `/membership` route, a later plan). Do not add it here. (Corrects the spec's Section 2 note.)
- **Deferred to Plan 4:** ComingSoon's calendar **view toggle + month navigation** (the HTMX calendar fragment). Plan 2 ships ComingSoon's **grid view** only. Also deferred: classics/membership/rentals/about pages.
- TDD: failing test first every task. Commit after each green task. SPA source to port from: `/Users/bgoding/code/SoftwareMaine/www_fortkentcinema_com`.

---

### Task 1: leprinceos service — date helpers (`web/services/showtimes.py`)

Ports the SPA's `src/utils/showtimeDates.js` to Python. Pure functions, no network — the cleanest first unit and a dependency of the movie transforms.

**Files:**
- Create: `web/services/__init__.py`, `web/services/showtimes.py`, `web/tests/test_showtimes.py`
- Reference: `/Users/bgoding/code/SoftwareMaine/www_fortkentcinema_com/src/utils/showtimeDates.js` (+ its test for cases)

**Interfaces:**
- Produces:
  - `CINEMA_TZ = ZoneInfo("America/New_York")`
  - `today_eastern() -> str` — `'YYYY-MM-DD'` for now in cinema tz
  - `format_showtime_date(date_str: str, weekday: str = "long", *, today: str | None = None) -> str` — returns `"Today"` when `date_str` equals today (pass `today` for determinism in tests), else e.g. `"Friday, Dec 31"` (`weekday="long"`) or `"Fri, Dec 31"` (`weekday="short"`)
  - `upcoming_dates(showtimes: dict | None, *, today: str | None = None) -> list[str]` — keys of `showtimes` that are `>= today`, sorted ascending; `[]` for falsy/non-dict input

- [ ] **Step 1: Write the failing test**

Create `web/services/__init__.py` (empty). Create `web/tests/test_showtimes.py`:

```python
import datetime
from django.test import SimpleTestCase
from web.services import showtimes


class ShowtimeDateTests(SimpleTestCase):
    def test_today_eastern_is_iso(self):
        self.assertRegex(showtimes.today_eastern(), r"^\d{4}-\d{2}-\d{2}$")

    def test_format_today_label(self):
        today = showtimes.today_eastern()
        self.assertEqual(showtimes.format_showtime_date(today, today=today), "Today")

    def test_format_long_and_short_weekday(self):
        # 2999-12-31 is a Friday; assert shape, not a hardcoded locale name.
        long = showtimes.format_showtime_date("2999-12-31", today="2000-01-01")
        self.assertRegex(long, r"^[A-Za-z]{4,}, Dec 31$")
        short = showtimes.format_showtime_date("2999-12-31", weekday="short", today="2000-01-01")
        self.assertRegex(short, r"^[A-Za-z]{3}, Dec 31$")
        self.assertNotEqual(short, long)

    def test_upcoming_dates_filters_and_sorts(self):
        today = "2999-01-01"
        st = {"2000-01-01": ["6:00 PM"], "2999-12-31": ["9:00 PM"],
              "2999-06-15": ["3:00 PM"], today: ["7:00 PM"]}
        self.assertEqual(
            showtimes.upcoming_dates(st, today=today),
            [today, "2999-06-15", "2999-12-31"],
        )

    def test_upcoming_dates_bad_input(self):
        for bad in (None, "nope", 123, []):
            self.assertEqual(showtimes.upcoming_dates(bad, today="2000-01-01"), [])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `source .venv/bin/activate && python manage.py test web.tests.test_showtimes`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.services.showtimes'`.

- [ ] **Step 3: Implement `web/services/showtimes.py`**

```python
"""Date helpers for showtime display — Python port of the SPA's
src/utils/showtimeDates.js. All logic runs in the cinema's local timezone so
"today" and labels match the box office, not the visitor's device."""
import datetime
from zoneinfo import ZoneInfo

CINEMA_TZ = ZoneInfo("America/New_York")


def today_eastern():
    return datetime.datetime.now(CINEMA_TZ).date().isoformat()


def format_showtime_date(date_str, weekday="long", *, today=None):
    if today is None:
        today = today_eastern()
    if date_str == today:
        return "Today"
    d = datetime.date.fromisoformat(date_str)
    # %A = full weekday, %a = abbreviated; %b = abbreviated month; %-d = day, no pad
    fmt = "%A, %b %-d" if weekday == "long" else "%a, %b %-d"
    return d.strftime(fmt)


def upcoming_dates(showtimes, *, today=None):
    if not isinstance(showtimes, dict):
        return []
    if today is None:
        today = today_eastern()
    return sorted(k for k in showtimes if k >= today)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python manage.py test web.tests.test_showtimes`
Expected: PASS (5 tests OK).

- [ ] **Step 5: Commit**

```bash
git add web/services/__init__.py web/services/showtimes.py web/tests/test_showtimes.py
git commit -m "feat(web): port showtime date helpers to Python (web.services.showtimes)"
```

---

### Task 2: leprinceos service — movie fetchers (`web/services/leprinceos.py`)

Ports `getNowShowing()` and `getComingSoon()` from `src/services/api.js` server-side: `requests` to leprinceos, UTC→Eastern conversion, grouping/dedup, plus a cache with TTL + stale fallback. Home needs exactly these two. (`getClassicMovieNight`/`getCalendarMonth` are deferred to Plan 4.)

**Files:**
- Create: `web/services/leprinceos.py`, `web/tests/test_leprinceos.py`
- Modify: `fortkentcinema/settings.py` (add `LEPRINCEOS_BASE_URL`, and a `CACHES` LocMem default if not already present)
- Reference: `/Users/bgoding/code/SoftwareMaine/www_fortkentcinema_com/src/services/api.js` (the `getNowShowing`, `getComingSoon`, and the format/group helpers)

**Interfaces:**
- Consumes: `web.services.showtimes` (`today_eastern`, `format_showtime_date` not needed here; uses tz + grouping).
- Produces:
  - `get_now_showing() -> list[dict]` — each: `{"id": str, "title": str, "rating": str, "runtime": str, "genre": "", "poster": str, "showtimes": {"YYYY-MM-DD": ["6:00 PM", ...]}, "youtube_id": str, "is_free_for_members": bool}` (only movies with ≥1 upcoming showtime date)
  - `get_coming_soon() -> list[dict]` — each: `{"id": str, "title": str, "start_date": "YYYY-MM-DD", "release_date": "Month D", "genre": "", "poster": str, "films": [{"id","title","poster"}], "description": str, "youtube_id": str, "is_free_for_members": bool}`
  - Internal: `_get(path, ttl=180) -> list|dict` (cache + stale fallback), `_format_showtime(utc_iso) -> "6:00 PM"`, `_local_date(utc_iso) -> "YYYY-MM-DD"`, `_format_runtime(minutes) -> "2h 16min"`

**Note on field naming:** the SPA used camelCase keys (`isFreeForMembers`, `youtube_id`, `startDate`, `releaseDate`). Use snake_case in Python dicts (`is_free_for_members`, `youtube_id`, `start_date`, `release_date`); templates will use the snake_case names. `youtube_id` stays `youtube_id`.

- [ ] **Step 1: Write the failing test** (mock `requests.get`; no network)

Create `web/tests/test_leprinceos.py`:

```python
from unittest import mock
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from web.services import leprinceos


def _resp(payload):
    m = mock.Mock()
    m.ok = True
    m.json.return_value = payload
    m.raise_for_status.return_value = None
    return m


class FormatHelpersTests(SimpleTestCase):
    def test_runtime(self):
        self.assertEqual(leprinceos._format_runtime(136), "2h 16min")
        self.assertEqual(leprinceos._format_runtime(60), "1h")
        self.assertEqual(leprinceos._format_runtime(45), "45min")
        self.assertEqual(leprinceos._format_runtime(None), "")

    def test_local_date_and_time_eastern(self):
        # 2025-01-15 00:30 UTC == 2025-01-14 19:30 America/New_York (EST)
        self.assertEqual(leprinceos._local_date("2025-01-15T00:30:00Z"), "2025-01-14")
        self.assertEqual(leprinceos._format_showtime("2025-01-15T00:30:00Z"), "7:30 PM")


class GetNowShowingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_groups_showtimes_by_local_date_and_filters_empty(self):
        engagements = [
            {"id": 1, "film_title": "Dune", "film_poster_url": "d.jpg",
             "films": [{"id": 9}], "is_free_for_members": True,
             "show_in_main_listings": True},
        ]
        showtimes = [
            # 18:00Z == 1:00 PM EST — two distinct Eastern dates
            {"id": 100, "starts_at": "2999-01-15T18:00:00Z"},
            {"id": 101, "starts_at": "2999-01-16T18:00:00Z"},
        ]
        film = {"rating": "PG-13", "runtime_minutes": 155, "youtube_id": "abc"}

        def fake_get(url, timeout=None):
            if "/engagements/?" in url:
                return _resp({"results": engagements})
            if "/showtimes/" in url:
                return _resp({"results": showtimes})
            if "/films/9" in url:
                return _resp(film)
            return _resp({"results": []})

        with mock.patch("web.services.leprinceos.requests.get", side_effect=fake_get):
            movies = leprinceos.get_now_showing()

        self.assertEqual(len(movies), 1)
        m = movies[0]
        self.assertEqual(m["id"], "1")
        self.assertEqual(m["title"], "Dune")
        self.assertEqual(m["rating"], "PG-13")
        self.assertEqual(m["runtime"], "2h 35min")
        self.assertEqual(m["youtube_id"], "abc")
        self.assertTrue(m["is_free_for_members"])
        # Two UTC times land on two distinct Eastern dates:
        self.assertEqual(sorted(m["showtimes"].keys()), ["2999-01-15", "2999-01-16"])
        self.assertEqual(m["showtimes"]["2999-01-15"], ["1:00 PM"])  # 18:00Z -> 1:00 PM EST

    def test_stale_fallback_on_error(self):
        engagements = [{"id": 2, "film_title": "X", "films": [],
                        "show_in_main_listings": True}]
        # Prime the cache via a successful engagements call, then fail.
        ok = _resp({"results": engagements})
        with mock.patch("web.services.leprinceos.requests.get", return_value=ok):
            leprinceos._get("/engagements/?status=CONFIRMED")
        boom = mock.Mock(side_effect=RuntimeError("down"))
        with mock.patch("web.services.leprinceos.requests.get", side_effect=boom):
            # After TTL, a failed refetch serves last-good instead of raising.
            cache.delete("lpos:/engagements/?status=CONFIRMED")  # expire fresh, keep stale
            data = leprinceos._get("/engagements/?status=CONFIRMED")
        self.assertEqual(data, engagements)
```

Note: the exact leprinceos query strings in `_get` calls come from porting `api.js`; adjust the test's cache keys to match the real paths you build if they differ — the behavior asserted (grouping, snake_case keys, runtime formatting, stale fallback) is the contract.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python manage.py test web.tests.test_leprinceos`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.services.leprinceos'`.

- [ ] **Step 3: Add settings**

In `fortkentcinema/settings.py`, add near the other config reads:

```python
LEPRINCEOS_BASE_URL = config(
    "LEPRINCEOS_BASE_URL", default="https://www.leprinceos.com/api/v1"
)
```

If no `CACHES` is defined, add the LocMem default (safe, no infra):

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fkc-local",
    }
}
```

- [ ] **Step 4: Implement `web/services/leprinceos.py`**

Port `api.js` faithfully. Structure (fill in the transform bodies from `api.js` — same logic, snake_case output keys):

```python
"""Server-side port of the SPA's src/services/api.js for the leprinceos
(cinema_sass) API. Fetches engagements/showtimes/films, converts UTC times to
America/New_York, and caches results with a stale-on-failure fallback."""
import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache

CINEMA_TZ = ZoneInfo("America/New_York")
BASE_URL = settings.LEPRINCEOS_BASE_URL


def _get(path, ttl=180):
    """GET BASE_URL+path, unwrap DRF 'results', cache for `ttl`s with a
    no-expiry stale copy served if a later refetch fails."""
    key = f"lpos:{path}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        resp = requests.get(BASE_URL + path, timeout=4)
        data = resp.json()
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        cache.set(key, results, ttl)
        cache.set(f"{key}:stale", results, None)
        return results
    except Exception:
        stale = cache.get(f"{key}:stale")
        return stale if stale is not None else []


def _format_showtime(utc_iso):
    dt = datetime.datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).astimezone(CINEMA_TZ)
    # e.g. "6:00 PM" — strip leading zero on the hour
    return dt.strftime("%I:%M %p").lstrip("0")


def _local_date(utc_iso):
    dt = datetime.datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).astimezone(CINEMA_TZ)
    return dt.date().isoformat()


def _format_runtime(minutes):
    if not minutes:
        return ""
    h, m = divmod(int(minutes), 60)
    if h == 0:
        return f"{m}min"
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}min"


def _primary_film_id(engagement):
    films = engagement.get("films") or []
    return films[0]["id"] if films else None


def get_now_showing():
    """Port of api.js getNowShowing(): confirmed engagements active in the next
    7 days, each with its showtimes grouped by local date. Returns only movies
    with at least one upcoming showtime date. See api.js for the exact query
    params (status=CONFIRMED, start_date_before, end_date_after) and the
    show_in_main_listings filter."""
    # ... port the api.js body: build today/seven-days strings in CINEMA_TZ,
    # fetch engagements, filter show_in_main_listings != False, for each fetch
    # /showtimes/?engagement=<id>&is_cancelled=false and (optional) /films/<id>/,
    # group showtimes via _local_date/_format_showtime, assemble the snake_case
    # dict, drop movies with empty showtimes. Use _get() for every call.
    ...


def get_coming_soon():
    """Port of api.js getComingSoon(): confirmed engagements starting tomorrow+,
    deduped by film set, kind != CLASSIC. Returns the snake_case shape in the
    Interfaces block. See api.js for query params and dedup logic."""
    ...
```

Implement the two `...` bodies by translating the corresponding `api.js` functions line-by-line (they are fully written there), using the helpers above and `settings.LEPRINCEOS_BASE_URL`. Keep `genre` as `""` (the SPA does). Build date strings (`today`, `seven_days`, `tomorrow`) with `datetime.datetime.now(CINEMA_TZ)`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python manage.py test web.tests.test_leprinceos`
Expected: PASS. Fix transforms until the grouping/format/stale assertions hold.

- [ ] **Step 6: Run the full suite**

Run: `python manage.py test`
Expected: all pass (Plan 1's 21 + the new service tests).

- [ ] **Step 7: Commit**

```bash
git add web/services/leprinceos.py web/tests/test_leprinceos.py fortkentcinema/settings.py
git commit -m "feat(web): port leprinceos now-showing/coming-soon fetchers with cached stale fallback"
```

---

### Task 3: Add Alpine.js + port the three remaining effect init modules

Adds Alpine (needed by the section templates) to `base.html`, and ports `useNeonPowerOn`, `useCursorBulbs`, `useCardSpotlight` into vanilla init modules wired into the effects boot. Rebuilds `static/js/effects.js`.

**Files:**
- Create: `frontend/effects/init/neonPowerOn.js`, `frontend/effects/init/cursorBulbs.js`, `frontend/effects/init/cardSpotlight.js`
- Modify: `frontend/effects/main.js` (boot the new inits), `templates/base.html` (add Alpine script, vendored)
- Create: `static/js/alpine.min.js` (vendored Alpine v3 — download once; committed, since CSP/self-hosting and no CDN at runtime)
- Modify: `static/js/effects.js` (rebuilt output)
- Reference: SPA `src/effects/hooks/useNeonPowerOn.js`, `useCursorBulbs.js`, `useCardSpotlight.js`

**Interfaces:**
- Produces:
  - `initNeonPowerOn(root=document)` — attaches to `[data-neon]` hero; replays the SPA's scripted sputter once per session (`sessionStorage` key `fkc-neon-power-on`), toggling `hero--pre-show`/`hero--live`, `bulb--lit`, and title opacity exactly as `useNeonPowerOn`. Dispatches a `neon:live` CustomEvent on the hero when live (so cursor bulbs can start).
  - `initCursorBulbs(root=document)` — on `[data-cursor-bulbs]`, when tier is `full` and after neon is live, drives `.bulb` transform/box-shadow from pointer proximity (port of `useCursorBulbs`).
  - `initCardSpotlight(root=document)` — on every `[data-spotlight]` grid, ports `useCardSpotlight` (spotlight div, focus/dim/tilt on `:scope > article`).
- Consumes: existing `core/pointer.js`, `core/motionPrefs.js` (+ `d3-scale`, `d3-ease` — add to `frontend/package.json` deps).

- [ ] **Step 1: Vendor Alpine + add to base.html**

Download Alpine v3 into the repo (one-time; committed for no-CDN runtime):

```bash
cd /Users/bgoding/code/SoftwareMaine/api_fortkentcinema_com
curl -sL https://unpkg.com/alpinejs@3.14.1/dist/cdn.min.js -o static/js/alpine.min.js
test -s static/js/alpine.min.js && echo OK
```

In `templates/base.html`, load Alpine with `defer` in `<head>` (Alpine requires `defer`), before the effects module at end of body is fine too, but Alpine convention is head+defer:

```django
    <script defer src="{% static 'js/alpine.min.js' %}"></script>
```

(Place it in `{% block extra_head %}`'s vicinity in base — add a dedicated line in the head after the GA snippet.)

- [ ] **Step 2: Add d3 deps for the effects build**

In `frontend/package.json` dependencies add `"d3-scale": "^4.0.2"` and `"d3-ease": "^3.0.1"`, then:

```bash
cd frontend && npm install
```

- [ ] **Step 3: Write a failing Vitest for cardSpotlight scaffolding**

Create `frontend/effects/__tests__/cardSpotlight.test.js` — assert that on a `full`-tier stub, `initCardSpotlight` adds the `fx-spotlight-grid` class and a `.fx-spotlight` child to a `[data-spotlight]` grid:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('initCardSpotlight', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div data-spotlight><article>a</article></div>';
    // Force getMotionTier() === 'full': matchMedia present, not reduced, fine pointer.
    vi.stubGlobal('matchMedia', (q) => ({
      matches: q.includes('reduce') ? false : q.includes('coarse') ? false : false,
    }));
  });

  it('adds spotlight scaffolding on full tier', async () => {
    const { initCardSpotlight } = await import('../init/cardSpotlight.js');
    initCardSpotlight(document);
    const grid = document.querySelector('[data-spotlight]');
    expect(grid.classList.contains('fx-spotlight-grid')).toBe(true);
    expect(grid.querySelector('.fx-spotlight')).not.toBeNull();
  });
});
```

Run: `cd frontend && npm test` → FAIL (module missing).

- [ ] **Step 4: Implement the three init modules**

Port each SPA hook to a DOM-scan init. `cardSpotlight.js` (port of `useCardSpotlight`, default selector `:scope > article`, idempotent via `dataset.spotlightInit`):

```js
import { onPointer } from '../core/pointer.js';
import { getMotionTier } from '../core/motionPrefs.js';

const MAX_TILT = 4;

function attach(grid, selector = ':scope > article') {
  if (getMotionTier() !== 'full') return;
  try {
    grid.classList.add('fx-spotlight-grid');
    const spot = document.createElement('div');
    spot.className = 'fx-spotlight';
    spot.setAttribute('aria-hidden', 'true');
    grid.appendChild(spot);
    let wasInside = false;
    const clearCards = () => grid.querySelectorAll(selector).forEach((card) => {
      card.classList.remove('fx-card--focus', 'fx-card--dim');
      card.style.transform = '';
    });
    onPointer((p) => {
      const rect = grid.getBoundingClientRect();
      const inside = p.sx >= rect.left && p.sx <= rect.right && p.sy >= rect.top && p.sy <= rect.bottom;
      grid.classList.toggle('fx-spotlight-grid--active', inside);
      if (!inside) { if (wasInside) { clearCards(); wasInside = false; } return; }
      wasInside = true;
      spot.style.transform = `translate(${p.sx - rect.left}px, ${p.sy - rect.top}px)`;
      grid.querySelectorAll(selector).forEach((card) => {
        const cr = card.getBoundingClientRect();
        const over = p.x >= cr.left && p.x <= cr.right && p.y >= cr.top && p.y <= cr.bottom;
        card.classList.toggle('fx-card--focus', over);
        card.classList.toggle('fx-card--dim', !over);
        if (over) {
          const center = cr.left + cr.width / 2;
          const tilt = ((p.sx - center) / (cr.width / 2)) * MAX_TILT;
          card.style.transform = `translateY(-6px) perspective(800px) rotateY(${tilt}deg)`;
        } else { card.style.transform = ''; }
      });
    });
  } catch (err) { console.error('[effects] card spotlight disabled:', err); }
}

export function initCardSpotlight(root = document) {
  root.querySelectorAll('[data-spotlight]').forEach((grid) => {
    if (grid.dataset.spotlightInit) return;
    grid.dataset.spotlightInit = '1';
    attach(grid);
  });
}
```

`neonPowerOn.js` — port `useNeonPowerOn` (constants `BULB_START=200`, `BULB_STAGGER=45`, `POWER_ON_TOTAL=2500`, the `FLICKER_STEPS` array, `POWER_ON_STORAGE_KEY='fkc-neon-power-on'`, `shouldSkip()` = static tier or already-played). On skip or completion, add `hero--live` and dispatch `hero.dispatchEvent(new CustomEvent('neon:live'))`. Idempotent via `dataset.neonInit`.

`cursorBulbs.js` — port `useCursorBulbs` (RADIUS=90, `scaleLinear`/`easeCubicOut` from d3). Only run when `getMotionTier() === 'full'`. Start listening after the hero's `neon:live` event (or immediately if the hero already has `hero--live`). Idempotent via `dataset.cursorBulbsInit`.

- [ ] **Step 5: Wire the boot**

Update `frontend/effects/main.js` `boot()` to also call `initNeonPowerOn(document)`, `initCursorBulbs(document)`, `initCardSpotlight(document)` (after the existing dust + reveal inits). Re-arm `initCardSpotlight` on `htmx:afterSwap` alongside `initScrollReveal`.

- [ ] **Step 6: Run Vitest, then build**

Run: `cd frontend && npm test` → PASS. Then `npm run build` → verify `static/js/effects.js` regenerated.

- [ ] **Step 7: Run the Django suite** (unaffected) and commit

```bash
cd .. && source .venv/bin/activate && python manage.py test 2>&1 | tail -3
git add frontend/ static/js/effects.js static/js/alpine.min.js templates/base.html
git commit -m "feat(effects): port neon power-on, cursor bulbs, card spotlight; vendor Alpine"
```

---

### Task 4: HomeView + page meta + OrnamentDivider partial

Replaces the placeholder `HomeView` with the real one (calls the service), overrides the home page's `<title>`/OG blocks to the SPA's home values, and ports the small `OrnamentDivider` used between sections.

**Files:**
- Modify: `web/views.py` (`HomeView.get_context_data`)
- Modify: `web/templates/web/home.html` (meta block overrides + composition skeleton; sections filled in Tasks 5–7)
- Create: `templates/partials/ornament_divider.html`
- Modify: `web/tests/test_pages.py`
- Reference: SPA `src/App.jsx` `HomePage` `<Helmet>` values + `OrnamentDivider` (App.jsx:25)

**Interfaces:**
- Consumes: `web.services.leprinceos.get_now_showing`, `get_coming_soon`.
- Produces: `HomeView` context keys `now_showing: list`, `coming_soon: list`; `home.html` overriding blocks `title`, `description`, `og_title`, `og_description`; `partials/ornament_divider.html` include.

- [ ] **Step 1: Write the failing test** (service mocked)

Add to `web/tests/test_pages.py`:

```python
from unittest import mock


class HomeViewDataTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_context_has_movie_lists(self, _ns, _cs):
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("now_showing", resp.context)
        self.assertIn("coming_soon", resp.context)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_home_meta_overrides(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Movies in the St. John Valley", html)  # home <title>/og:title
```

- [ ] **Step 2: Run → fail** (`get_now_showing` not imported in views / title not overridden).

Run: `python manage.py test web.tests.test_pages`

- [ ] **Step 3: Implement `HomeView`**

```python
from django.views.generic import TemplateView
from web.services.leprinceos import get_now_showing, get_coming_soon


class HomeView(TemplateView):
    template_name = "web/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["now_showing"] = get_now_showing()
        ctx["coming_soon"] = get_coming_soon()
        return ctx
```

- [ ] **Step 4: home.html meta + skeleton**

Rewrite `web/templates/web/home.html` to override meta and lay out the section include points (sections added in Tasks 5–7; use empty placeholders for now so the page renders):

```django
{% extends "base.html" %}
{% load static %}

{% block title %}Fort Kent Cinema | Movies in the St. John Valley{% endblock %}
{% block description %}Fort Kent Cinema - Your local movie theater in Fort Kent, Maine. Check showtimes, coming soon, and join our membership program.{% endblock %}
{% block og_title %}Fort Kent Cinema | Movies in the St. John Valley{% endblock %}
{% block og_description %}Your local movie theater in Fort Kent, Maine. Check showtimes, coming soon, and join our membership program.{% endblock %}

{% block extra_css %}
  {# section sheets linked here as Tasks 5–7 add them #}
{% endblock %}

{% block content %}
  {# Task 5 #}{# hero + classic CTA #}
  {% include "partials/now_showing.html" %}
  {# Task 6 #}{# open-mic CTA + coming soon #}
  {# Task 7 #}{# gift-card CTA + blog teaser #}
{% endblock %}
```

Since `partials/now_showing.html` doesn't exist yet, temporarily comment its include out (or create an empty stub) so this task's tests pass; Task 5 creates it and un-stubs. **Create an empty `templates/partials/now_showing.html` stub** with a single comment line to keep the include valid.

Create `templates/partials/ornament_divider.html` by porting `OrnamentDivider` from `src/App.jsx:25` (preserve its exact markup/classes).

- [ ] **Step 5: Run → pass**, then full suite.

Run: `python manage.py test web.tests.test_pages && python manage.py test`

- [ ] **Step 6: Commit**

```bash
git add web/views.py web/templates/web/home.html templates/partials/ornament_divider.html web/tests/test_pages.py
git commit -m "feat(web): real HomeView with service data + home meta + ornament divider"
```

---

### Task 5: Hero + ClassicMovieCTA + NowShowing (with Alpine date nav & trailer modal)

The core of the page. Ports the Hero (neon/cursor hooks), the ClassicMovieCTA promo, and NowShowing — the latter with **all** showtime data server-rendered and Alpine handling date navigation, the trailer modal, and the phone/desktop split via CSS.

**Files:**
- Create: `templates/partials/hero.html`, `templates/partials/cta_classic.html`, `templates/partials/now_showing.html` (replaces the stub), `templates/partials/movie_card.html`, `templates/partials/movie_schedule_card.html`
- Modify: `web/templates/web/home.html` (link Hero/NowShowing/ClassicCTA sheets; add hero + classic CTA into composition)
- Modify: `web/tests/test_pages.py`
- Reference: SPA `src/components/Hero/Hero.jsx`, `ClassicMovieCTA/ClassicMovieCTA.jsx`, `NowShowing/NowShowing.jsx`, `MovieCard/MovieCard.jsx`, `MovieScheduleCard/MovieScheduleCard.jsx`

**Interfaces:**
- Consumes: `now_showing` context; `site_config`; effect hooks `data-neon`, `data-cursor-bulbs`, `data-spotlight`; date helpers — precompute in the view (see Step 1).
- Produces: `partials/hero.html`, `partials/now_showing.html` (+ movie card partials), `partials/cta_classic.html`.

**View support — precompute date structures** (Alpine needs them in the DOM). Extend `HomeView.get_context_data` to add, for Now Showing:
- `ns_dates`: sorted list of upcoming date keys across all movies (`YYYY-MM-DD`)
- `ns_dates_labeled`: `[{"key","label"}]` using `format_showtime_date`
- `ns_today`: `today_eastern()`
- For each movie, keep its `showtimes` dict (already keyed by date) so the template can render per-date showtime buttons.

- [ ] **Step 1: Write the failing test**

Add to `web/tests/test_pages.py` (`HomeViewDataTests` or a new class) with a mocked `get_now_showing` returning one movie with two dates:

```python
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing")
    def test_now_showing_renders_movie_and_dates(self, ns, _cs):
        ns.return_value = [{
            "id": "1", "title": "Dune", "rating": "PG-13", "runtime": "2h 35min",
            "genre": "", "poster": "d.jpg", "youtube_id": "abc",
            "is_free_for_members": True,
            "showtimes": {"2999-01-15": ["6:00 PM"], "2999-01-16": ["7:00 PM"]},
        }]
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("now-showing", html)          # section id
        self.assertIn("Dune", html)                  # movie title
        self.assertIn("6:00 PM", html)               # a showtime rendered into DOM
        self.assertIn("Free for Members", html)      # free banner
        self.assertIn('data-spotlight', html)        # spotlight grid hook
        self.assertIn('data-neon', html)             # hero neon hook
```

- [ ] **Step 2: Run → fail** (partials/ hooks missing).

- [ ] **Step 3: Port Hero → `partials/hero.html`**

Transcribe `Hero.jsx` markup verbatim (preserve every class: `hero`, `hero-background`, `hero-stars`, `hero-pines`, `light-spill`, `marquee-*`, `bulb`, `marquee-title/subtitle`, `hero-tagline`, `hero-cta`, `btn btn-ticket`, `btn btn-secondary`). Replace:
- `ref={heroRef}` → `data-neon data-cursor-bulbs` on the `<section class="hero">`.
- The bulb loops (`topBulbs` 17 each for top+bottom, `sideBulbs` 5 each left+right) → Django `{% for %}` ranges: `{% for i in "xxxxxxxxxxxxxxxxx" %}` is ugly; instead pass ranges from the view or use `{% for i in ns_bulb_top %}`. Simplest: add context lists `hero_top_bulbs = range(17)` and `hero_side_bulbs = range(5)` in the view, loop them.
- `cinema.name.toUpperCase()` → `{{ site_config.cinema.name|upper }}`; tagline similarly; `heroQuote` into `.hero-tagline`.
- `<Link to="/membership">` → `<a href="/membership">`; `<a href="#now-showing">` stays.
Link the sheet: add `<link rel="stylesheet" href="{% static 'css/Hero.css' %}">` via `home.html`'s `{% block extra_css %}`.

- [ ] **Step 4: Port ClassicMovieCTA → `partials/cta_classic.html`**

Transcribe `ClassicMovieCTA.jsx` verbatim (static promo — preserve classes). Link `ClassicMovieCTA.css`.

- [ ] **Step 5: Port NowShowing → `partials/now_showing.html` with Alpine**

Transcribe `NowShowing.jsx` structure. Interactivity mapping:
- Wrap the section in an Alpine component: `x-data="{ dates: {{ ns_dates_json }}, idx: {{ ns_today_index }}, trailer: null }"` (pass `ns_dates_json` as a JSON list of date keys, `ns_today_index` = index of today or 0).
- **Desktop date nav:** render the `date-nav` with prev/next buttons bound to `@click="idx = Math.max(0, idx-1)"` / `idx = Math.min(dates.length-1, idx+1)`, `:disabled` at bounds, and the label showing the current date's human label. Render the movie grid so each movie's showtimes for EACH date are present but only the active date's block is shown: put per-date show blocks with `x-show="dates[idx] === '<date>'"`. Precompute per movie a list of `{date, label, times[]}` in the view to loop cleanly.
- **Movie grid:** `<div class="movies-grid" data-spotlight>` looping movies → `{% include "partials/movie_card.html" %}`.
- **Phone schedule list:** render `<div class="schedule-list">` looping `{% include "partials/movie_schedule_card.html" %}`. Desktop grid and phone list are BOTH rendered; visibility is controlled by NowShowing.css's existing responsive rules (verify the CSS already switches on `max-width: 600px`; if the SPA relied on JS `isPhone`, add a `@media` rule in a tiny additional stylesheet or inline — but first check `NowShowing.css`; prefer its existing breakpoints).
- **Trailer modal:** one modal per section bound to Alpine `trailer` state; poster click sets `trailer = {id, title, youtube_id}`; the modal `x-show="trailer"` builds the youtube-nocookie iframe `:src`. Port the overlay markup (`now-trailer-*`) verbatim, replacing React handlers with Alpine `@click`/`x-show`/`:src`. Lock body scroll with `x-effect="document.body.style.overflow = trailer ? 'hidden' : ''"`.
- `formatShowtimeDate` labels come from the view (`ns_dates_labeled`).

- [ ] **Step 6: Port MovieCard + MovieScheduleCard partials**

`movie_card.html` — transcribe `MovieCard.jsx` (classes `movie-card`, `movie-poster(--playable)`, `movie-free-banner`, `movie-poster-img`, `poster-placeholder*`, `movie-poster-play-overlay/icon`, `movie-info`, `movie-title/meta/rating/runtime/genre`, `movie-showtimes`, `showtime`). Poster click → Alpine `@click="trailer = {...}"` when `movie.youtube_id`. Showtime buttons render the passed date's times (from the Alpine-active date). Free banner when `movie.is_free_for_members`. Image `onerror` fallback → keep the `<img onerror>` inline handler or a small CSS/JS fallback (a plain `onerror="this.style.display='none'"` inline attribute is acceptable and matches SPA behavior).

`movie_schedule_card.html` — transcribe `MovieScheduleCard.jsx` (phone view): header thumb + meta, `schedule-card__dates` list of upcoming dates (use the movie's upcoming dates + labels precomputed in the view), showtime buttons, and the "Show all N dates" toggle via Alpine `x-data="{ expanded: false }"` with `x-show` on the dates beyond the first 3 (`INITIAL_DATE_COUNT = 3`). Trailer poster click sets the section's `trailer` state.

- [ ] **Step 7: Wire into home.html + link sheets**

In `home.html`: add `{% include "partials/hero.html" %}`, `ornament_divider`, `cta_classic`, `ornament_divider` before the NowShowing include (already present). Add `<link>`s for `Hero.css`, `ClassicMovieCTA.css`, `NowShowing.css`, `MovieCard.css`, `MovieScheduleCard.css` in `{% block extra_css %}`.

- [ ] **Step 8: Run tests → pass**, then full suite. Manually spot-check with `runserver` + a mocked/live service that the marquee, date nav, and a trailer modal work.

Run: `python manage.py test web && python manage.py test`

- [ ] **Step 9: Commit**

```bash
git add templates/partials/hero.html templates/partials/cta_classic.html templates/partials/now_showing.html templates/partials/movie_card.html templates/partials/movie_schedule_card.html web/templates/web/home.html web/views.py web/tests/test_pages.py
git commit -m "feat(web): Hero + ClassicMovieCTA + NowShowing (Alpine date nav, trailer modal, spotlight)"
```

---

### Task 6: OpenMicCTA + ComingSoon (grid view)

Ports the OpenMicCTA promo and ComingSoon's **grid view** (the default) with its trailer modal and card spotlight. The calendar view toggle + month nav are deferred to Plan 4; render the grid only, and omit the view-toggle buttons for now (or render them disabled/hidden — see Step 4).

**Files:**
- Create: `templates/partials/cta_openmic.html`, `templates/partials/coming_soon.html`
- Modify: `web/templates/web/home.html`, `web/tests/test_pages.py`
- Reference: SPA `src/components/OpenMicCTA/OpenMicCTA.jsx`, `ComingSoon/ComingSoon.jsx` (grid branch only)

**Interfaces:**
- Consumes: `coming_soon` context.
- Produces: `partials/cta_openmic.html`, `partials/coming_soon.html`.

- [ ] **Step 1: Write the failing test**

```python
    @mock.patch("web.views.get_now_showing", return_value=[])
    @mock.patch("web.views.get_coming_soon")
    def test_coming_soon_grid_renders(self, cs, _ns):
        cs.return_value = [{
            "id": "5", "title": "Wicked", "release_date": "November 22",
            "genre": "", "poster": "w.jpg", "youtube_id": "", "films": [],
            "is_free_for_members": False, "start_date": "2999-11-22",
        }]
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("coming-soon", html)
        self.assertIn("Wicked", html)
        self.assertIn("NOVEMBER 22", html)  # release_date uppercased in template
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Port OpenMicCTA → `partials/cta_openmic.html`** (verbatim static promo; link `OpenMicCTA.css`).

- [ ] **Step 4: Port ComingSoon grid → `partials/coming_soon.html`**

Transcribe the ComingSoon `<section class="coming-soon" id="coming-soon">` and the **grid branch** (`coming-movies-grid` with `data-spotlight`). Preserve classes: `coming-movie-card`, `coming-movie-poster(--playable)`, `coming-free-banner`, `coming-poster-multi/img(--multi)`, `coming-poster-placeholder(--multi)`, `coming-poster-icon`, `coming-poster-play-overlay/icon`, `coming-movie-info/date/title/genre`. Multi-film double-features render each film poster (loop `movie.films`). Trailer modal (`coming-trailer-*`) via the same Alpine pattern as NowShowing (section-scoped `x-data="{ trailer: null }"`).
- **View toggle + calendar:** the SPA renders a grid/calendar toggle. For Plan 2, render ONLY the grid; **omit the `coming-view-toggle` buttons and the calendar branch entirely** (a comment notes Plan 4 adds them). This keeps the section functional and correct without the deferred HTMX calendar.
- `release_date` → `{{ movie.release_date|upper }}`. Link `ComingSoon.css`.

- [ ] **Step 5: Wire into home.html** — after NowShowing: `ornament_divider`, `cta_openmic`, `ornament_divider`, `coming_soon`. Add `OpenMicCTA.css` + `ComingSoon.css` links.

- [ ] **Step 6: Run tests → pass; full suite.**

- [ ] **Step 7: Commit**

```bash
git add templates/partials/cta_openmic.html templates/partials/coming_soon.html web/templates/web/home.html web/tests/test_pages.py
git commit -m "feat(web): OpenMicCTA + ComingSoon grid view (trailer modal, spotlight; calendar deferred to Plan 4)"
```

---

### Task 7: GiftCardCTA + Blog teaser + composition finalize

Ports the final two home sections and finalizes the full composition + phone-stripping, then adds an integration test that the whole page renders end-to-end with mocked data.

**Files:**
- Create: `templates/partials/cta_giftcard.html`, `templates/partials/blog_teaser.html`
- Modify: `web/templates/web/home.html`, `web/views.py` (blog teaser data), `web/tests/test_pages.py`
- Reference: SPA `src/components/GiftCardCTA/GiftCardCTA.jsx`, `src/components/Blog/Blog.jsx` (home teaser)

**Interfaces:**
- Consumes: latest 3 `BlogPost` (native model) for the teaser; `now_showing`/`coming_soon` already wired.
- Produces: `partials/cta_giftcard.html`, `partials/blog_teaser.html`; finalized `home.html`.

- [ ] **Step 1: Write the failing integration test**

```python
class HomeIntegrationTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_full_home_composition_order(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        # Sections appear in the SPA's order
        order = [html.index(s) for s in (
            'class="hero"', 'id="now-showing"', 'id="coming-soon"',
        )]
        self.assertEqual(order, sorted(order))
        self.assertIn("ornament", html)          # dividers present
        self.assertIn('data-ambient-dust', html) # base chrome intact
```

Add a Blog-teaser test: create 1 `BlogPost` (+ author/category) in `setUpTestData` and assert its title appears on the home page.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Port GiftCardCTA → `partials/cta_giftcard.html`** (verbatim; link `GiftCardCTA.css`).

- [ ] **Step 4: Port Blog teaser → `partials/blog_teaser.html`**

Transcribe `Blog.jsx` (the home teaser — preserve classes; link `Blog.css`). Feed it the latest 3 posts. In `HomeView.get_context_data` add `ctx["recent_posts"] = BlogPost.objects.all()[:3]` (model default ordering is `-post_date`). Loop them in the teaser; each links to `/blog/<slug>` (blog detail is Plan 3 — the link target is fine to render now).

- [ ] **Step 5: Finalize `home.html` composition**

Full ordered composition with `ornament_divider` between each, matching the Global Constraints order. Add phone-stripping: wrap Hero, all four CTAs, and the Blog teaser (the desktop-only sections) so they hide on phones. The SPA hides them below 600px — verify each section's CSS already does this; if not, add a small `templates` `{% block extra_css %}` rule or a shared `home.css` with `@media (max-width: 600px){ .hero, .classic-cta, .openmic-cta, .giftcard-cta, .blog-section { display:none } }` (use the actual root class names from each component's CSS). Confirm against the source CSS which sections already self-hide to avoid double rules.

- [ ] **Step 6: Run tests → pass; full suite.** Manual `runserver` sweep: full page renders top-to-bottom, effects boot, a trailer opens, date nav works, no template-comment leaks.

- [ ] **Step 7: Commit**

```bash
git add templates/partials/cta_giftcard.html templates/partials/blog_teaser.html web/templates/web/home.html web/views.py web/tests/test_pages.py
git commit -m "feat(web): GiftCardCTA + Blog teaser + finalize home composition & phone-stripping"
```

---

## Self-Review

**Spec coverage (design doc Section 2 "HomePage" + Section 4 service):**
- leprinceos service (fetch + cache + stale) → Tasks 1–2. Timezone via `zoneinfo` → Task 1/2.
- Home page sections (Hero, NowShowing, ComingSoon, CTAs, Blog teaser) → Tasks 4–7. **Correction logged:** Membership is NOT on home (spec Section 2 was inaccurate); it's the `/membership` route in a later plan.
- Effects (neon, cursor bulbs, card spotlight) → Task 3. HTMX re-arm hook for spotlight → Task 3 Step 5.
- Interactivity via Alpine (date nav, trailer modal, schedule-card expand) with data server-rendered → Tasks 5–6.
- **Deferred (documented):** ComingSoon calendar view toggle + month HTMX nav → Plan 4; classics/membership/rentals/about → Plan 4; blog detail page → Plan 3 (home teaser links to it now, which is fine).

**Placeholder scan:** The two `...` bodies in Task 2 Step 4 (`get_now_showing`/`get_coming_soon`) are explicit "translate this exact api.js function" instructions with the helper signatures, input query params, and output shape fully specified + a test that pins the behavior — not hand-waving. The Task 4 `now_showing.html` stub is a deliberate, named two-step (stub in Task 4, replaced in Task 5) to keep each task's tests green.

**Type/name consistency:** service output keys are snake_case throughout (`is_free_for_members`, `start_date`, `release_date`, `youtube_id`) and templates/tests use those exact names. Effect init names (`initNeonPowerOn`/`initCursorBulbs`/`initCardSpotlight`) match between the modules (Task 3 Step 4), `main.js` boot (Step 5), and the Vitest (Step 3). `data-neon`/`data-cursor-bulbs`/`data-spotlight` attributes match between the partials (Tasks 5–6) and the init scanners (Task 3). Context keys (`now_showing`, `coming_soon`, `recent_posts`, `ns_dates*`) are consistent across `views.py` and the templates that consume them.
