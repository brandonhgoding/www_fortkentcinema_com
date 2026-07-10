# Dashboard Films + TMDB + FilmSearch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the film-picker infrastructure — a TMDB service, film search + import-from-TMDB endpoints, and the `FilmSearchCombo` as an Alpine/HTMX combobox — so the Engagements sub-project can drop it into its create/edit drawer.

**Architecture:** Verbatim-port the leprinceos TMDB `requests` client + cached service into `cinema/tmdb/`; a `cinema.services.import_film_from_tmdb` helper creates-or-reuses a `Film`; staff-gated `dashboard` views return HTML fragments for local search, TMDB search, and import; the combobox is an Alpine component whose options are HTMX-swapped server fragments, emitting a `film-selected` event both consumers converge on.

**Tech Stack:** Django 5.2, `requests`, HTMX + Alpine (vendored), Django `TestCase` with mocked `requests`.

## Global Constraints

- Verbatim CSS/service ports are exact `cp` copies from `/Users/bgoding/code/SoftwareMaine` sources (leprinceos): `api_leprinceos_com/films/tmdb/client.py`, `.../services.py`, and `www_leprinceos_com/src/components/FilmSearchCombo/FilmSearchCombo.module.css`.
- TMDB module lives in `cinema/tmdb/`; the import helper in `cinema/services.py`. This sub-project MAY extend the `cinema` app (models untouched — `Film` already has the fields). All other new code lives in `dashboard/` + `fortkentcinema/settings.py`/`urls.py`.
- `TMDB_API_KEY` comes from env (default `""`). Tests MUST mock `requests` — never hit the real TMDB API. No key required to build or test.
- Import from TMDB is idempotent: reuse an existing `Film` with the same `tmdb_id`.
- All dashboard endpoints use `dashboard.mixins.StaffRequiredMixin` and live under `/dashboard/films/`.
- Reuse the Foundation Toast (`window.dashboardToast`) via the existing `dashboard-toast` HX-Trigger bridge; CSRF is already wired globally (`hx-headers` on `<body>`).
- Tests use `django.test.TestCase`, run with `python manage.py test dashboard cinema`.
- Run from repo root `api_fortkentcinema_com/` with `source .venv/bin/activate`.

---

### Task 1: TMDB service (verbatim port) + settings

**Files:**
- Create: `cinema/tmdb/__init__.py`, `cinema/tmdb/client.py` (verbatim), `cinema/tmdb/services.py` (verbatim), `cinema/tmdb/tests/__init__.py`, `cinema/tmdb/tests/test_tmdb.py`
- Modify: `fortkentcinema/settings.py` (TMDB settings)

**Interfaces:**
- Produces: `cinema.tmdb.services.TMDBService` with `search_films(query, page=1) -> list[dict]` (normalized: `tmdb_id`, `title`, `release_date`, `overview`, `poster_path` full URL, `backdrop_path`, `runtime`, `genres`, `vote_average`, `popularity`) and `get_film_details(tmdb_id) -> dict` (adds `runtime`, `genres`, `imdb_id`); `cinema.tmdb.client.TMDBClient`, `TMDBAPIError`.

- [ ] **Step 1: Add TMDB settings**

Append to `fortkentcinema/settings.py`:

```python
# TMDB (The Movie Database) integration
TMDB_API_KEY = config("TMDB_API_KEY", default="")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/"
```

- [ ] **Step 2: Copy the client + service verbatim**

```bash
mkdir -p cinema/tmdb/tests
cp /Users/bgoding/code/SoftwareMaine/api_leprinceos_com/films/tmdb/client.py cinema/tmdb/client.py
cp /Users/bgoding/code/SoftwareMaine/api_leprinceos_com/films/tmdb/services.py cinema/tmdb/services.py
```

Create `cinema/tmdb/__init__.py`:

```python
from .client import TMDBAPIError, TMDBClient
from .services import TMDBService

__all__ = ["TMDBClient", "TMDBService", "TMDBAPIError"]
```

Create `cinema/tmdb/tests/__init__.py` (empty).

The copied files import `from django.conf import settings` and (in services) `from .client import TMDBClient` — both correct in this location. They read `settings.TMDB_API_KEY`/`TMDB_BASE_URL`/`TMDB_IMAGE_BASE_URL` added in Step 1.

- [ ] **Step 3: Write the failing tests**

Create `cinema/tmdb/tests/test_tmdb.py`:

```python
from unittest import mock

from cinema.tmdb import TMDBAPIError, TMDBClient, TMDBService
from django.core.cache import cache
from django.test import TestCase, override_settings

import requests


@override_settings(TMDB_API_KEY="testkey", TMDB_BASE_URL="https://api.tmdb/3",
                   TMDB_IMAGE_BASE_URL="https://img.tmdb/")
class TMDBClientTests(TestCase):
    def test_requires_key(self) -> None:
        with override_settings(TMDB_API_KEY=""):
            with self.assertRaises(ValueError):
                TMDBClient()

    def test_build_image_url(self) -> None:
        c = TMDBClient()
        self.assertEqual(c.build_image_url(None), "")
        self.assertEqual(c.build_image_url("/p.jpg", size="w500"), "https://img.tmdb/w500/p.jpg")

    @mock.patch("cinema.tmdb.client.requests.get")
    def test_search_movies_ok(self, mget) -> None:
        mget.return_value = mock.Mock(status_code=200,
                                      json=lambda: {"results": [{"id": 1, "title": "A"}]})
        mget.return_value.raise_for_status = lambda: None
        data = TMDBClient().search_movies("a")
        self.assertEqual(data["results"][0]["title"], "A")

    @mock.patch("cinema.tmdb.client.requests.get")
    def test_http_error_becomes_tmdb_error(self, mget) -> None:
        resp = mock.Mock(status_code=401)
        resp.json = lambda: {"status_message": "bad"}
        err = requests.exceptions.HTTPError(response=resp)
        m = mock.Mock()
        m.raise_for_status.side_effect = err
        mget.return_value = m
        with self.assertRaises(TMDBAPIError) as ctx:
            TMDBClient().search_movies("a")
        self.assertEqual(ctx.exception.status_code, 401)


@override_settings(TMDB_API_KEY="testkey", TMDB_BASE_URL="https://api.tmdb/3",
                   TMDB_IMAGE_BASE_URL="https://img.tmdb/")
class TMDBServiceTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    @mock.patch("cinema.tmdb.client.requests.get")
    def test_search_films_normalizes_and_caches(self, mget) -> None:
        payload = {"results": [{"id": 7, "title": "Nope", "release_date": "2022-08-19",
                                "overview": "o", "poster_path": "/p.jpg", "vote_average": 7.5}]}
        m = mock.Mock(json=lambda: payload)
        m.raise_for_status = lambda: None
        mget.return_value = m
        out = TMDBService().search_films("nope")
        self.assertEqual(out[0]["tmdb_id"], 7)
        self.assertEqual(out[0]["poster_path"], "https://img.tmdb/w500/p.jpg")
        self.assertEqual(out[0]["runtime"], None)
        # Second call is cached -> requests.get not called again
        TMDBService().search_films("nope")
        self.assertEqual(mget.call_count, 1)

    @mock.patch("cinema.tmdb.client.requests.get")
    def test_get_film_details(self, mget) -> None:
        payload = {"id": 7, "title": "Nope", "runtime": 130, "imdb_id": "tt1",
                   "genres": [{"name": "Horror"}], "poster_path": "/p.jpg"}
        m = mock.Mock(json=lambda: payload)
        m.raise_for_status = lambda: None
        mget.return_value = m
        d = TMDBService().get_film_details(7)
        self.assertEqual(d["runtime"], 130)
        self.assertEqual(d["genres"], ["Horror"])
        self.assertEqual(d["imdb_id"], "tt1")
```

- [ ] **Step 4: Run tests to verify they fail, then pass**

Run: `python manage.py test cinema.tmdb.tests.test_tmdb -v 2`
Before the copy (Step 2 undone) it FAILS on import. After Steps 1–2 it PASSES (6 tests). Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cinema/tmdb/ fortkentcinema/settings.py
git commit -m "feat(cinema): port TMDB client + service (mocked tests, key from env)"
```

---

### Task 2: import_film_from_tmdb helper

**Files:**
- Create: `cinema/services.py`
- Create: `cinema/tests/test_services.py`

**Interfaces:**
- Consumes: `TMDBService.get_film_details`, `cinema.models.Film`.
- Produces: `cinema.services.import_film_from_tmdb(tmdb_id: int, service=None) -> Film` — reuse-or-create by `tmdb_id`.

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_services.py`:

```python
from unittest import mock

from cinema.models import Film
from cinema.services import import_film_from_tmdb
from django.test import TestCase

DETAILS = {
    "tmdb_id": 42, "title": "The Answer", "release_date": "2001-01-01",
    "overview": "o", "poster_path": "https://img/x.jpg", "backdrop_path": "https://img/b.jpg",
    "runtime": 108, "genres": ["Sci-Fi"], "imdb_id": "tt42",
}


class ImportFilmFromTMDBTests(TestCase):
    def test_creates_film(self) -> None:
        svc = mock.Mock()
        svc.get_film_details.return_value = DETAILS
        film = import_film_from_tmdb(42, service=svc)
        self.assertEqual(film.title, "The Answer")
        self.assertEqual(film.tmdb_id, "42")
        self.assertEqual(film.runtime_minutes, 108)
        self.assertEqual(film.imdb_id, "tt42")
        self.assertEqual(film.poster_url, "https://img/x.jpg")

    def test_reuses_existing_by_tmdb_id(self) -> None:
        existing = Film.objects.create(title="Old", tmdb_id="42")
        svc = mock.Mock()
        film = import_film_from_tmdb(42, service=svc)
        self.assertEqual(film.pk, existing.pk)
        svc.get_film_details.assert_not_called()  # no fetch when reusing
        self.assertEqual(Film.objects.filter(tmdb_id="42").count(), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_services -v 2`
Expected: FAIL — `cinema.services` missing.

- [ ] **Step 3: Implement the helper**

Create `cinema/services.py`:

```python
from __future__ import annotations

from .models import Film
from .tmdb.services import TMDBService


def import_film_from_tmdb(tmdb_id: int, service: TMDBService | None = None) -> Film:
    """Create a Film from TMDB details, or reuse an existing one with the same tmdb_id."""
    existing = Film.objects.filter(tmdb_id=str(tmdb_id)).first()
    if existing is not None:
        return existing

    svc = service or TMDBService()
    details = svc.get_film_details(tmdb_id)
    return Film.objects.create(
        title=details.get("title", ""),
        tmdb_id=str(details["tmdb_id"]) if details.get("tmdb_id") else None,
        imdb_id=details.get("imdb_id") or "",
        poster_url=details.get("poster_path") or "",
        backdrop_url=details.get("backdrop_path") or "",
        overview=details.get("overview") or "",
        runtime_minutes=details.get("runtime"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test cinema.tests.test_services -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add cinema/services.py cinema/tests/test_services.py
git commit -m "feat(cinema): import_film_from_tmdb (reuse-or-create by tmdb_id)"
```

---

### Task 3: Local + TMDB film search endpoints

**Files:**
- Create: `dashboard/templates/dashboard/_film_options.html`, `dashboard/templates/dashboard/_tmdb_options.html`
- Modify: `dashboard/views.py` (`FilmSearchView`, `FilmSearchTMDBView`), `dashboard/urls.py`
- Create: `dashboard/tests/test_films.py`

**Interfaces:**
- Consumes: `cinema.models.Film`, `cinema.tmdb.services.TMDBService`, `cinema.tmdb.TMDBAPIError`.
- Produces: `dashboard:film_search` (`GET ?q=`), `dashboard:film_search_tmdb` (`GET ?q=`) returning option fragments; option buttons emit/lead to `film-selected`.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_films.py`:

```python
from unittest import mock

from cinema.models import Film
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class FilmSearchTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_local_search_matches(self) -> None:
        Film.objects.create(title="Jaws", runtime_minutes=124)
        Film.objects.create(title="Dune", runtime_minutes=155)
        html = self.client.get(reverse("dashboard:film_search"), {"q": "jaw"}).content.decode()
        self.assertIn("Jaws", html)
        self.assertNotIn("Dune", html)
        self.assertIn("Search TMDB", html)  # the TMDB affordance
        self.assertIn(reverse("dashboard:film_search_tmdb"), html)

    def test_local_search_empty_q(self) -> None:
        html = self.client.get(reverse("dashboard:film_search"), {"q": ""}).content.decode()
        self.assertNotIn("Search TMDB", html)

    @mock.patch("dashboard.views.TMDBService")
    def test_tmdb_search_renders_results(self, MockSvc) -> None:
        MockSvc.return_value.search_films.return_value = [
            {"tmdb_id": 5, "title": "Alien", "release_date": "1979-05-25",
             "overview": "space horror", "poster_path": "https://img/a.jpg", "vote_average": 8.4}
        ]
        html = self.client.get(reverse("dashboard:film_search_tmdb"), {"q": "alien"}).content.decode()
        self.assertIn("Alien", html)
        self.assertIn("1979", html)
        self.assertIn("TMDB Results", html)

    @mock.patch("dashboard.views.TMDBService")
    def test_tmdb_search_error_inline(self, MockSvc) -> None:
        from cinema.tmdb import TMDBAPIError
        MockSvc.return_value.search_films.side_effect = TMDBAPIError("boom")
        resp = self.client.get(reverse("dashboard:film_search_tmdb"), {"q": "x"})
        self.assertEqual(resp.status_code, 200)  # not a 500
        self.assertIn("Couldn't reach TMDB", resp.content.decode())

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:film_search")).status_code, 302)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_films -v 2`
Expected: FAIL — views/routes absent.

- [ ] **Step 3: Create the option fragments**

`dashboard/templates/dashboard/_film_options.html`:

```html
{% load static %}
{% if q %}
  {% if films %}
    <div class="sectionHeader">Your Films</div>
    {% for film in films %}
    <button type="button" class="resultItem" role="option"
            @click="$dispatch('film-selected', {id: {{ film.id }}, title: '{{ film.title|escapejs }}', poster: '{{ film.poster_url|escapejs }}'}); selectDone()">
      <div class="posterWrapper">
        {% if film.poster_url %}<img src="{{ film.poster_url }}" alt="" class="poster" />
        {% else %}<div class="posterPlaceholder"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>{% endif %}
      </div>
      <div class="resultContent">
        <div class="resultTitle">{{ film.title }}{% if film.runtime_minutes %}<span class="resultMeta">{{ film.runtime_minutes }} min</span>{% endif %}</div>
        {% if film.rating %}<span class="resultRating">{{ film.rating }}</span>{% endif %}
      </div>
    </button>
    {% endfor %}
  {% else %}
    <div class="emptyLocalState"><p class="emptyText">No films found for "{{ q }}"</p></div>
  {% endif %}
  <div class="divider"></div>
  <button type="button" class="tmdbOption" role="option"
          hx-get="{% url 'dashboard:film_search_tmdb' %}?q={{ q|urlencode }}"
          hx-target="#tmdb-results" hx-swap="innerHTML">
    <svg class="tmdbIcon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
    <span>Search TMDB for "{{ q }}"</span>
  </button>
  <div id="tmdb-results"></div>
{% endif %}
```

`dashboard/templates/dashboard/_tmdb_options.html`:

```html
{% if error %}
  <div class="emptyState"><p class="emptyText">Couldn't reach TMDB. Try again.</p></div>
{% elif results %}
  <div class="sectionHeader">
    <svg class="sectionIcon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
    TMDB Results
  </div>
  {% for r in results %}
  <button type="button" class="resultItem tmdbResultItem" role="option"
          hx-post="{% url 'dashboard:film_from_tmdb' %}" hx-vals='{"tmdb_id": {{ r.tmdb_id }}}' hx-swap="none">
    <div class="posterWrapper">
      {% if r.poster_path %}<img src="{{ r.poster_path }}" alt="" class="poster" />
      {% else %}<div class="posterPlaceholder"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>{% endif %}
    </div>
    <div class="resultContent">
      <div class="resultTitle">{{ r.title }}{% if r.release_date %}<span class="resultYear">({{ r.release_date|slice:":4" }})</span>{% endif %}</div>
      {% if r.overview %}<p class="resultOverview">{{ r.overview|truncatechars:100 }}</p>{% endif %}
      {% if r.vote_average %}<div class="tmdbRating"><svg class="starIcon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>{{ r.vote_average|floatformat:1 }}</div>{% endif %}
    </div>
  </button>
  {% endfor %}
{% else %}
  <div class="emptyState"><p class="emptyText">No TMDB results for "{{ q }}"</p></div>
{% endif %}
```

- [ ] **Step 4: Implement the search views**

In `dashboard/views.py` add (imports: `from cinema.tmdb import TMDBAPIError`, `from cinema.tmdb.services import TMDBService`, `from cinema.models import Film` already present):

```python
class FilmSearchView(StaffRequiredMixin, View):
    def get(self, request):
        q = request.GET.get("q", "").strip()
        films = Film.objects.filter(title__icontains=q)[:8] if q else Film.objects.none()
        return render(request, "dashboard/_film_options.html", {"q": q, "films": films})


class FilmSearchTMDBView(StaffRequiredMixin, View):
    def get(self, request):
        q = request.GET.get("q", "").strip()
        ctx = {"q": q, "results": [], "error": False}
        if q:
            try:
                ctx["results"] = TMDBService().search_films(q)
            except (TMDBAPIError, ValueError):
                ctx["error"] = True
        return render(request, "dashboard/_tmdb_options.html", ctx)
```

Add routes to `dashboard/urls.py`:

```python
    path("films/search", views.FilmSearchView.as_view(), name="film_search"),
    path("films/search/tmdb", views.FilmSearchTMDBView.as_view(), name="film_search_tmdb"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_films -v 2`
Expected: PASS (5 tests). Then `python manage.py test dashboard cinema` → all green.

- [ ] **Step 6: Commit**

```bash
git add dashboard/ 
git commit -m "feat(dashboard): local + TMDB film search fragment endpoints"
```

---

### Task 4: Import-from-TMDB endpoint

**Files:**
- Modify: `dashboard/views.py` (`FilmFromTMDBView`), `dashboard/urls.py`
- Modify: `dashboard/tests/test_films.py` (import tests)

**Interfaces:**
- Consumes: `cinema.services.import_film_from_tmdb`.
- Produces: `dashboard:film_from_tmdb` (POST `tmdb_id`) → HTTP 204 with `HX-Trigger` firing `film-selected` ({id,title,poster}) + `dashboard-toast`; on error → `dashboard-toast` error, no film added.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_films.py`:

```python
import json


class FilmFromTMDBTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    @mock.patch("dashboard.views.import_film_from_tmdb")
    def test_import_fires_film_selected(self, mimport) -> None:
        film = Film.objects.create(title="Imported", tmdb_id="99", poster_url="https://img/p.jpg")
        mimport.return_value = film
        resp = self.client.post(reverse("dashboard:film_from_tmdb"), {"tmdb_id": 99})
        self.assertEqual(resp.status_code, 204)
        trigger = json.loads(resp["HX-Trigger"])
        self.assertEqual(trigger["film-selected"]["id"], film.id)
        self.assertEqual(trigger["film-selected"]["title"], "Imported")
        self.assertIn("dashboard-toast", trigger)

    @mock.patch("dashboard.views.import_film_from_tmdb")
    def test_import_error_toasts(self, mimport) -> None:
        from cinema.tmdb import TMDBAPIError
        mimport.side_effect = TMDBAPIError("nope")
        resp = self.client.post(reverse("dashboard:film_from_tmdb"), {"tmdb_id": 1})
        self.assertEqual(resp.status_code, 204)
        trigger = json.loads(resp["HX-Trigger"])
        self.assertNotIn("film-selected", trigger)
        self.assertEqual(trigger["dashboard-toast"]["kind"], "error")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_films.FilmFromTMDBTests -v 2`
Expected: FAIL — route/view absent.

- [ ] **Step 3: Implement the import view**

In `dashboard/views.py` add (imports: `from cinema.services import import_film_from_tmdb`, `from cinema.tmdb import TMDBAPIError` already added in Task 3, `import json`, `from django.http import HttpResponse` already present):

```python
class FilmFromTMDBView(StaffRequiredMixin, View):
    def post(self, request):
        tmdb_id = request.POST.get("tmdb_id")
        resp = HttpResponse(status=204)
        try:
            film = import_film_from_tmdb(int(tmdb_id))
        except (TMDBAPIError, ValueError, TypeError):
            resp["HX-Trigger"] = json.dumps(
                {"dashboard-toast": {"kind": "error", "message": "Failed to add film from TMDB."}}
            )
            return resp
        resp["HX-Trigger"] = json.dumps({
            "film-selected": {"id": film.id, "title": film.title, "poster": film.poster_url},
            "dashboard-toast": {"kind": "success", "message": f"Added {film.title}"},
        })
        return resp
```

Add the route to `dashboard/urls.py`:

```python
    path("films/from-tmdb", views.FilmFromTMDBView.as_view(), name="film_from_tmdb"),
```

Note: `ValueError` covers `int(None)`/`int("")`; `TMDBAPIError` covers a live-fetch failure inside `import_film_from_tmdb`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_films -v 2`
Expected: PASS (all film tests). Then `python manage.py test dashboard cinema` → green.

- [ ] **Step 5: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): import-from-TMDB endpoint firing film-selected"
```

---

### Task 5: FilmSearchCombo partial + Alpine + CSS

**Files:**
- Create: `dashboard/static/dashboard/css/film_search_combo.css` (verbatim copy)
- Create: `dashboard/templates/dashboard/_film_search_combo.html`
- Modify: `dashboard/static/dashboard/js/dashboard.js` (`filmCombo` Alpine component)
- Modify: `dashboard/tests/test_films.py` (combo render test)

**Interfaces:**
- Consumes: `dashboard:film_search`; the `film-selected` event contract.
- Produces: an includable combobox `{% include "dashboard/_film_search_combo.html" with combo_id="..." %}` with a debounced search input and dropdown; `Alpine.data('filmCombo', …)` handling open/close/keyboard/click-outside + `selectDone()`.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_films.py`:

```python
from pathlib import Path
from django.conf import settings as dj_settings


class FilmComboTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_combo_css_byte_identical(self) -> None:
        src = Path("/Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/components/FilmSearchCombo/FilmSearchCombo.module.css").read_bytes()
        dest = Path(dj_settings.BASE_DIR) / "dashboard/static/dashboard/css/film_search_combo.css"
        self.assertEqual(dest.read_bytes(), src)

    def test_filmcombo_registered(self) -> None:
        js = (Path(dj_settings.BASE_DIR) / "dashboard/static/dashboard/js/dashboard.js").read_text()
        self.assertIn("Alpine.data('filmCombo'", js)
```

(The combo partial is exercised for real by the Engagements sub-project; here we verify the verbatim CSS and the Alpine registration. A render smoke test is added in Step 4 below.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_films.FilmComboTests -v 2`
Expected: FAIL — css/js absent.

- [ ] **Step 3: Copy the combo CSS verbatim**

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/components/FilmSearchCombo/FilmSearchCombo.module.css \
   dashboard/static/dashboard/css/film_search_combo.css
```

- [ ] **Step 4: Create the combo partial**

`dashboard/templates/dashboard/_film_search_combo.html`:

```html
<div class="container" x-data="filmCombo" @click.outside="open = false">
  <div class="searchWrapper">
    <input type="text" class="input" placeholder="Search for a film..."
           name="q" autocomplete="off"
           aria-autocomplete="list" :aria-expanded="open"
           @focus="open = true"
           @keydown.arrow-down.prevent="move(1)"
           @keydown.arrow-up.prevent="move(-1)"
           @keydown.escape.prevent="open = false"
           hx-get="{% url 'dashboard:film_search' %}"
           hx-trigger="keyup changed delay:300ms"
           hx-target="#{{ combo_id|default:'film-combo' }}-results"
           hx-swap="innerHTML"
           @htmx:after-request="open = true" />
    <div class="inputSpinner htmx-indicator" aria-label="Searching">
      <svg class="spinner" viewBox="0 0 24 24"><circle class="spinnerCircle" cx="12" cy="12" r="10" fill="none" stroke-width="3"/></svg>
    </div>
    <div id="{{ combo_id|default:'film-combo' }}-results" class="dropdown" role="listbox" x-show="open" x-cloak></div>
  </div>
  <p class="helpText" x-show="!open">Search your films or find new ones on TMDB.</p>
</div>
```

- [ ] **Step 5: Add the filmCombo Alpine component**

Append to `dashboard/static/dashboard/js/dashboard.js`:

```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('filmCombo', () => ({
    open: false,
    // Called from an option button after a local selection: clear + close.
    selectDone() {
      this.open = false;
      const input = this.$root.querySelector('input[name="q"]');
      if (input) input.value = '';
      const results = this.$root.querySelector('.dropdown');
      if (results) results.innerHTML = '';
    },
    // Roving focus across the rendered option buttons.
    move(dir) {
      this.open = true;
      const items = Array.from(this.$root.querySelectorAll('.dropdown button'));
      if (!items.length) return;
      const idx = items.indexOf(document.activeElement);
      const next = Math.max(0, Math.min(items.length - 1, idx + dir));
      items[next].focus();
    },
  }));
});

// When a film is imported from TMDB, the option button lives inside a combo;
// close/clear that combo after the server fires film-selected.
document.body.addEventListener('film-selected', (e) => {
  const combos = document.querySelectorAll('[x-data="filmCombo"]');
  combos.forEach((c) => {
    const input = c.querySelector('input[name="q"]');
    if (input) input.value = '';
    const results = c.querySelector('.dropdown');
    if (results) results.innerHTML = '';
  });
});
```

- [ ] **Step 6: Add a combo render smoke test**

Append to `FilmComboTests` in `dashboard/tests/test_films.py`:

```python
    def test_combo_partial_renders(self) -> None:
        from django.template.loader import render_to_string
        html = render_to_string("dashboard/_film_search_combo.html", {"combo_id": "eng-film"})
        self.assertIn('x-data="filmCombo"', html)
        self.assertIn('id="eng-film-results"', html)
        self.assertIn(reverse("dashboard:film_search"), html)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_films.FilmComboTests -v 2`
Expected: PASS (3 tests). Then `python manage.py test dashboard cinema` → green.

- [ ] **Step 8: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): FilmSearchCombo partial + Alpine component + verbatim CSS"
```

---

### Task 6: Final verification

**Files:** none (verification only).

- [ ] **Step 1: System + migration checks**

Run: `python manage.py check` → no issues.
Run: `python manage.py makemigrations --check --dry-run` → `No changes detected` (no model changes; `Film` already has the fields).

- [ ] **Step 2: Targeted suites**

Run: `python manage.py test cinema dashboard -v 2`
Expected: PASS (TMDB client/service, import helper, film search/tmdb/import endpoints, combo).

- [ ] **Step 3: Whole project suite (no regressions)**

Run: `python manage.py test`
Expected: PASS — `web`/`blog`/`cinema`/`dashboard`.

- [ ] **Step 4: Manual (needs a real TMDB_API_KEY in .env)**

Add `TMDB_API_KEY=…` to `.env`, `runserver`, and (once the Engagements form hosts the combo, or via a scratch template) type in the film search: local films appear, "Search TMDB" returns live results, clicking one adds a Film and fires a success toast. Without a key, TMDB search shows the inline "Couldn't reach TMDB" row (the `ValueError` from `TMDBClient` with no key is caught) — confirm this graceful degradation.

---

## Self-Review

**Spec coverage:**
- TMDB service verbatim in `cinema/tmdb/` + settings + mocked tests → Task 1. ✅
- `import_film_from_tmdb` reuse-or-create → Task 2. ✅
- Local search + TMDB search fragment endpoints (error not 500) → Task 3. ✅
- Import-from-TMDB firing `film-selected` + toast, dedupe → Tasks 2+4. ✅
- FilmSearchCombo Alpine partial + verbatim CSS, `film-selected` contract → Task 5. ✅
- Staff-gated, `/dashboard/films/`, reuse Toast/HX-Trigger, CSRF already global → Tasks 3–5. ✅
- No permanent demo route; combo verified via render + endpoints → Task 5. ✅

**Placeholder scan:** No vague steps; verbatim ports are exact `cp` from named sources; all new views/templates/JS/tests inlined. Step 4 in Task 1 notes the RED state pre-copy.

**Type consistency:** `TMDBService().search_films/get_film_details` shapes match `import_film_from_tmdb` and the fragment fields (`poster_path` full URL, `release_date`, `vote_average`). `film-selected` detail `{id,title,poster}` is identical in `FilmFromTMDBView` (server) and `_film_options.html` (client `$dispatch`), and consumed by the `film-selected` body listener. `film_search`/`film_search_tmdb`/`film_from_tmdb` URL names match across templates, views, and tests. `combo_id` defaults to `film-combo` consistently in the partial. `TMDBService` is imported into `dashboard.views` so the tests' `@mock.patch("dashboard.views.TMDBService")` and `@mock.patch("dashboard.views.import_film_from_tmdb")` patch the right symbols.
