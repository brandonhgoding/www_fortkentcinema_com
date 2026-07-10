# leprinceos → cinema Data Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A re-runnable `import_leprinceos --flush` management command that pulls films/engagements/showtimes from the leprinceos public API and rewrites the native `cinema` tables to match (screens reconstructed from FK references).

**Architecture:** A testable service `cinema/leprinceos_import.py` (`fetch_all` paginator + `import_all` orchestrator, one `transaction.atomic()`, returns counts) with a thin management-command wrapper. Screens are rebuilt from the `screen`/`screen_name` refs in engagements + showtimes; double-feature film order is preserved via `EngagementFilm.position`.

**Tech Stack:** Django 5.2, `requests`, Django `TestCase` (HTTP mocked — no live calls in tests).

## Global Constraints

- Data source default is `settings.LEPRINCEOS_BASE_URL` (`https://www.leprinceos.com/api/v1`). Public endpoints: `/films/`, `/engagements/`, `/showtimes/` (DRF-paginated). `/screens/` is auth-gated — do NOT call it; reconstruct screens from FK refs.
- Import mode is full **wipe + fresh**, all inside one `transaction.atomic()` (all-or-nothing). The wipe only happens with an explicit `--flush`; `import_all(flush=False)` must raise and write nothing.
- Screen import uses `capacity=capacity_default` (default **1**) + model-default specs (the API never exposes capacity/specs).
- Preserve double-feature film order: `EngagementFilm.position` = the record's `films` array index + 1.
- `Showtime.starts_at` parsed to an aware datetime from the API's ISO string (which carries an offset).
- Tests NEVER hit the network — mock `fetch_all` (or the injected session). Only `cinema/` files change; do NOT touch models, `dashboard/`, or `web/`.
- Tests: `python manage.py test cinema`. Run from repo root with `source .venv/bin/activate`.

---

### Task 1: Paginated fetch helper

**Files:**
- Create: `cinema/leprinceos_import.py`
- Create: `cinema/tests/test_leprinceos_import.py`

**Interfaces:**
- Produces: `cinema.leprinceos_import.fetch_all(base_url, path, *, session=None) -> list[dict]` — GET `base_url + path`, follow DRF `next` pagination, unwrap `results`, return all records. Uses `session` (a `requests.Session`-like with `.get`) if provided, else `requests`.

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_leprinceos_import.py`:

```python
import datetime
from unittest import mock

from cinema.leprinceos_import import fetch_all
from django.test import TestCase


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class FetchAllTests(TestCase):
    def test_follows_pagination(self) -> None:
        page1 = {"results": [{"id": 1}, {"id": 2}], "next": "https://api/x/?page=2"}
        page2 = {"results": [{"id": 3}], "next": None}
        session = mock.Mock()
        session.get.side_effect = [_Resp(page1), _Resp(page2)]
        out = fetch_all("https://api/x", "/films/", session=session)
        self.assertEqual([r["id"] for r in out], [1, 2, 3])
        # first call hits base+path, second follows the absolute `next` url
        first_url = session.get.call_args_list[0].args[0]
        second_url = session.get.call_args_list[1].args[0]
        self.assertEqual(first_url, "https://api/x/films/")
        self.assertEqual(second_url, "https://api/x/?page=2")

    def test_unwraps_plain_list(self) -> None:
        session = mock.Mock()
        session.get.side_effect = [_Resp([{"id": 9}])]
        out = fetch_all("https://api/x", "/films/", session=session)
        self.assertEqual(out, [{"id": 9}])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_leprinceos_import.FetchAllTests -v 2`
Expected: FAIL — `cinema.leprinceos_import` missing.

- [ ] **Step 3: Implement `fetch_all`**

Create `cinema/leprinceos_import.py`:

```python
from __future__ import annotations

import datetime

import requests
from django.db import transaction

from .models import Engagement, EngagementFilm, Film, Screen, Showtime

REQUEST_TIMEOUT = 15


def fetch_all(base_url: str, path: str, *, session=None) -> list[dict]:
    """GET base_url+path and follow DRF `next` pagination, returning all records.

    `session` is any object with a `.get(url, timeout=...)` method (a
    requests.Session in production, a mock in tests); defaults to `requests`.
    """
    client = session or requests
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    records: list[dict] = []
    while url:
        resp = client.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "results" in data:
            records.extend(data["results"])
            url = data.get("next")
        else:
            records.extend(data)
            url = None
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test cinema.tests.test_leprinceos_import.FetchAllTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add cinema/leprinceos_import.py cinema/tests/test_leprinceos_import.py
git commit -m "feat(cinema): paginated fetch_all for the leprinceos import"
```

---

### Task 2: `import_all` orchestrator

**Files:**
- Modify: `cinema/leprinceos_import.py` (add `import_all` + helpers)
- Modify: `cinema/tests/test_leprinceos_import.py` (import tests)

**Interfaces:**
- Consumes: `fetch_all`, `cinema` models.
- Produces: `import_all(base_url, *, flush, capacity_default=1, session=None) -> dict[str, int]` returning counts `{"screens","films","engagements","engagement_films","showtimes"}`. Raises `ValueError` if `flush` is False.

- [ ] **Step 1: Write the failing test**

Append to `cinema/tests/test_leprinceos_import.py`:

```python
from cinema.leprinceos_import import import_all
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime

FILMS = [
    {"id": 10, "title": "Alpha", "runtime_minutes": 90, "rating": "PG", "synopsis": "s",
     "poster_url": "http://p/a.jpg", "backdrop_url": "", "overview": "", "tmdb_id": None,
     "imdb_id": "tt10", "youtube_id": None},
    {"id": 11, "title": "Beta", "runtime_minutes": 100, "rating": "R", "synopsis": "",
     "poster_url": "", "backdrop_url": "", "overview": "", "tmdb_id": "", "imdb_id": "",
     "youtube_id": ""},
]
ENGAGEMENTS = [
    {"id": 20, "kind": "REGULAR", "event_title": "", "screen": 1, "screen_name": "The Century",
     "start_date": "2026-02-01", "end_date": "2026-02-07", "presentation_format": "2d",
     "status": "CONFIRMED", "show_in_main_listings": True, "notes": "hi",
     "films": [{"id": 10, "title": "Alpha", "poster_url": "http://p/a.jpg", "runtime_minutes": 90}]},
    {"id": 21, "kind": "DOUBLE_FEATURE", "event_title": "Creature Night", "screen": 2,
     "screen_name": "The Savoy", "start_date": "2026-03-01", "end_date": "2026-03-02",
     "presentation_format": "2d", "status": "CONFIRMED", "show_in_main_listings": False, "notes": "",
     "films": [{"id": 11, "title": "Beta"}, {"id": 10, "title": "Alpha"}]},
]
SHOWTIMES = [
    {"id": 30, "engagement": 20, "screen": 1, "screen_name": "The Century",
     "starts_at": "2026-02-01T19:30:00-05:00", "is_cancelled": False, "captions": "CC"},
    {"id": 31, "engagement": 21, "screen": 2, "screen_name": "The Savoy",
     "starts_at": "2026-03-01T20:00:00-05:00", "is_cancelled": True, "captions": None},
]


def _fake_fetch(base_url, path, *, session=None):
    return {"/films/": FILMS, "/engagements/": ENGAGEMENTS, "/showtimes/": SHOWTIMES}[path]


class ImportAllTests(TestCase):
    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_counts_and_rows(self, _f) -> None:
        counts = import_all("http://api", flush=True)
        self.assertEqual(counts["films"], 2)
        self.assertEqual(counts["screens"], 2)          # reconstructed: id 1 + id 2
        self.assertEqual(counts["engagements"], 2)
        self.assertEqual(counts["engagement_films"], 3)  # 1 + 2
        self.assertEqual(counts["showtimes"], 2)
        self.assertEqual(Screen.objects.count(), 2)
        self.assertEqual({s.name for s in Screen.objects.all()}, {"The Century", "The Savoy"})
        self.assertTrue(all(s.capacity == 1 for s in Screen.objects.all()))

    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_empty_external_ids_nulled(self, _f) -> None:
        import_all("http://api", flush=True)
        beta = Film.objects.get(title="Beta")
        self.assertIsNone(beta.tmdb_id)
        self.assertIsNone(beta.imdb_id)

    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_double_feature_ordering(self, _f) -> None:
        import_all("http://api", flush=True)
        eng = Engagement.objects.get(event_title="Creature Night")
        pairs = list(eng.engagement_films.values_list("film__title", "position"))
        self.assertEqual(pairs, [("Beta", 1), ("Alpha", 2)])

    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_showtime_tz_aware(self, _f) -> None:
        import_all("http://api", flush=True)
        st = Showtime.objects.get(is_cancelled=False)
        self.assertIsNotNone(st.starts_at.tzinfo)
        # 2026-02-01T19:30:00-05:00 == 2026-02-02T00:30:00Z
        self.assertEqual(st.starts_at.astimezone(datetime.timezone.utc).isoformat(),
                         "2026-02-02T00:30:00+00:00")

    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_flush_clears_prior_rows(self, _f) -> None:
        Screen.objects.create(name="Junk", capacity=5)
        import_all("http://api", flush=True)
        self.assertFalse(Screen.objects.filter(name="Junk").exists())

    def test_requires_flush(self) -> None:
        with self.assertRaises(ValueError):
            import_all("http://api", flush=False)
        self.assertEqual(Screen.objects.count(), 0)  # nothing written
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_leprinceos_import.ImportAllTests -v 2`
Expected: FAIL — `import_all` not defined.

- [ ] **Step 3: Implement `import_all`**

Append to `cinema/leprinceos_import.py`:

```python
def _parse_dt(value: str) -> datetime.datetime:
    # API sends ISO with an offset, e.g. "2026-02-01T19:30:00-05:00" -> aware.
    return datetime.datetime.fromisoformat(value)


def import_all(base_url, *, flush, capacity_default=1, session=None) -> dict[str, int]:
    """Wipe and rebuild the cinema tables from the leprinceos API. All-or-nothing.

    Raises ValueError if flush is not True (guards accidental data loss).
    """
    if not flush:
        raise ValueError("import_all requires flush=True (full wipe + fresh import).")

    films_raw = fetch_all(base_url, "/films/", session=session)
    engagements_raw = fetch_all(base_url, "/engagements/", session=session)
    showtimes_raw = fetch_all(base_url, "/showtimes/", session=session)

    counts = {"screens": 0, "films": 0, "engagements": 0, "engagement_films": 0, "showtimes": 0}

    with transaction.atomic():
        # 1. Flush child-first.
        Showtime.objects.all().delete()
        EngagementFilm.objects.all().delete()
        Engagement.objects.all().delete()
        Film.objects.all().delete()
        Screen.objects.all().delete()

        # 2. Screens reconstructed from FK refs in engagements + showtimes.
        screen_names: dict[int, str] = {}
        for e in engagements_raw:
            if e.get("screen") is not None:
                screen_names.setdefault(e["screen"], e.get("screen_name") or f"Screen {e['screen']}")
        for s in showtimes_raw:
            if s.get("screen") is not None:
                screen_names.setdefault(s["screen"], s.get("screen_name") or f"Screen {s['screen']}")
        screen_map: dict[int, Screen] = {}
        for sid, name in screen_names.items():
            screen_map[sid] = Screen.objects.create(name=name, capacity=capacity_default)
        counts["screens"] = len(screen_map)

        # 3. Films.
        film_map: dict[int, Film] = {}
        for f in films_raw:
            film_map[f["id"]] = Film.objects.create(
                title=f.get("title", ""),
                runtime_minutes=f.get("runtime_minutes"),
                rating=f.get("rating") or "",
                synopsis=f.get("synopsis") or "",
                poster_url=f.get("poster_url") or "",
                backdrop_url=f.get("backdrop_url") or "",
                overview=f.get("overview") or "",
                tmdb_id=f.get("tmdb_id") or "",
                imdb_id=f.get("imdb_id") or "",
                youtube_id=f.get("youtube_id") or "",
            )
        counts["films"] = len(film_map)

        # 4. Engagements + ordered EngagementFilm rows.
        eng_map: dict[int, Engagement] = {}
        for e in engagements_raw:
            screen = screen_map.get(e.get("screen"))
            if screen is None:
                continue
            eng = Engagement.objects.create(
                screen=screen,
                start_date=e["start_date"],
                end_date=e["end_date"],
                kind=e.get("kind", "REGULAR"),
                event_title=e.get("event_title") or "",
                presentation_format=e.get("presentation_format", "2d"),
                status=e.get("status", "DRAFT"),
                show_in_main_listings=bool(e.get("show_in_main_listings", True)),
                notes=e.get("notes") or "",
            )
            eng_map[e["id"]] = eng
            counts["engagements"] += 1
            for pos, f in enumerate(e.get("films") or [], start=1):
                film = film_map.get(f["id"])
                if film is None:
                    continue
                EngagementFilm.objects.create(engagement=eng, film=film, position=pos)
                counts["engagement_films"] += 1

        # 5. Showtimes.
        for s in showtimes_raw:
            eng = eng_map.get(s.get("engagement"))
            screen = screen_map.get(s.get("screen"))
            if eng is None or screen is None:
                continue
            Showtime.objects.create(
                engagement=eng,
                screen=screen,
                starts_at=_parse_dt(s["starts_at"]),
                is_cancelled=bool(s.get("is_cancelled", False)),
                captions=s.get("captions") or None,
            )
            counts["showtimes"] += 1

    return counts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test cinema.tests.test_leprinceos_import.ImportAllTests -v 2`
Expected: PASS (6 tests). Then `python manage.py test cinema` → green.

- [ ] **Step 5: Commit**

```bash
git add cinema/leprinceos_import.py cinema/tests/test_leprinceos_import.py
git commit -m "feat(cinema): import_all orchestrator (wipe + rebuild from API)"
```

---

### Task 3: Management command wrapper

**Files:**
- Create: `cinema/management/__init__.py`, `cinema/management/commands/__init__.py`, `cinema/management/commands/import_leprinceos.py`
- Modify: `cinema/tests/test_leprinceos_import.py` (command tests)

**Interfaces:**
- Consumes: `import_all`, `settings.LEPRINCEOS_BASE_URL`.
- Produces: `manage.py import_leprinceos [--flush] [--base-url URL] [--capacity N]`.

- [ ] **Step 1: Write the failing test**

Append to `cinema/tests/test_leprinceos_import.py`:

```python
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError


class CommandTests(TestCase):
    @mock.patch("cinema.leprinceos_import.fetch_all", side_effect=_fake_fetch)
    def test_command_with_flush_imports(self, _f) -> None:
        out = StringIO()
        call_command("import_leprinceos", "--flush", "--base-url", "http://api", stdout=out)
        self.assertEqual(Film.objects.count(), 2)
        self.assertIn("films", out.getvalue().lower())

    def test_command_without_flush_writes_nothing(self) -> None:
        with self.assertRaises(CommandError):
            call_command("import_leprinceos", "--base-url", "http://api")
        self.assertEqual(Film.objects.count(), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_leprinceos_import.CommandTests -v 2`
Expected: FAIL — unknown command `import_leprinceos`.

- [ ] **Step 3: Create the command package + command**

Create `cinema/management/__init__.py` (empty) and `cinema/management/commands/__init__.py` (empty).

Create `cinema/management/commands/import_leprinceos.py`:

```python
from cinema.leprinceos_import import import_all
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Import films/engagements/showtimes from the leprinceos API into the cinema tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true",
            help="Required. Wipe the cinema tables and rebuild from the API.",
        )
        parser.add_argument("--base-url", default=settings.LEPRINCEOS_BASE_URL)
        parser.add_argument("--capacity", type=int, default=1)

    def handle(self, *args, **options):
        if not options["flush"]:
            raise CommandError(
                "This command wipes and rebuilds the cinema tables. "
                "Re-run with --flush to proceed."
            )
        counts = import_all(
            options["base_url"], flush=True, capacity_default=options["capacity"]
        )
        summary = ", ".join(f"{k}={v}" for k, v in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Imported: {summary}"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test cinema.tests.test_leprinceos_import.CommandTests -v 2`
Expected: PASS (2 tests). Then `python manage.py test cinema` → green.

- [ ] **Step 5: Commit**

```bash
git add cinema/management/ cinema/tests/test_leprinceos_import.py
git commit -m "feat(cinema): import_leprinceos management command (--flush required)"
```

---

### Task 4: Final verification + live smoke

**Files:** none (verification only).

- [ ] **Step 1: System + migration checks**

Run: `python manage.py check` → `System check identified no issues`.
Run: `python manage.py makemigrations --check --dry-run` → `No changes detected` (no model changes).

- [ ] **Step 2: Cinema + full suite**

Run: `python manage.py test cinema -v 2` → PASS (fetch, import, command).
Run: `python manage.py test` → PASS (no regressions across web/blog/cinema/dashboard).

- [ ] **Step 3: Guard check — no `--flush`, no writes**

Run: `python manage.py import_leprinceos`
Expected: exits with the "Re-run with --flush" error; a follow-up `python manage.py shell -c "from cinema.models import Film; print(Film.objects.count())"` is unchanged.

- [ ] **Step 4: Live smoke (manual, dev DB — real API)**

Run: `python manage.py import_leprinceos --flush`
Expected: prints `Imported: screens=2, films=66, engagements=46, engagement_films=<≥47>, showtimes=397` (counts approximate to live data). Then confirm in the dashboard (`runserver`, `/dashboard/engagements` and a Details page) that real engagements/showtimes render, and that re-running the command reproduces the same state. (This step hits the live API and mutates the dev DB — expected.)

---

## Self-Review

**Spec coverage:**
- `fetch_all` paginator → Task 1. ✅
- `import_all` (flush guard, one transaction, screen reconstruction, films, engagements + ordered EngagementFilm, tz-aware showtimes, counts) → Task 2. ✅
- `import_leprinceos --flush` command (default base-url from settings, capacity arg, guard) → Task 3. ✅
- Tests mock HTTP; only cinema/ changes; no model edits → all tasks + Global Constraints. ✅
- Verification incl. live smoke → Task 4. ✅
- Out-of-scope items (screen specs, PK/created_at preservation, delta sync) → not present. ✅

**Placeholder scan:** No TBD/vague steps; all code inlined. `test_showtime_tz_aware` (Task 2) asserts a precise UTC instant; `import datetime` is included at the top of the test module (Task 1 Step 1).

**Type consistency:** `fetch_all(base_url, path, *, session=None)` signature matches its `import_all` calls and the command. `import_all(base_url, *, flush, capacity_default=1, session=None) -> dict` matches the command's `import_all(options["base_url"], flush=True, capacity_default=...)`. Count keys (`screens/films/engagements/engagement_films/showtimes`) match between `import_all` and the command summary + tests. `screen_map`/`film_map`/`eng_map` used consistently. `_parse_dt` returns aware datetimes fed to `Showtime.starts_at`. The Task-1 `fetch_all` implementation imports the cinema models at module top (used by `import_all` added in Task 2) — harmless in Task 1.
