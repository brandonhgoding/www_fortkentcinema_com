# Public Site → cinema ORM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the public pages' cinema data (Now Showing, Coming Soon, Calendar, Classics) from the native `cinema` tables via the ORM instead of the leprinceos HTTP API, preserving the exact return shapes so views/templates are unchanged.

**Architecture:** A new `web/services/cinema_data.py` reproduces the four service functions from the ORM with byte-identical return shapes; `web/views.py`'s import is repointed; `web/services/leprinceos.py` (and its HTTP-mock test) is deleted. No request-time cache.

**Tech Stack:** Django 5.2 (USE_TZ, TIME_ZONE=America/New_York), Django `TestCase`.

## Global Constraints

- Reproduce the EXACT return shapes of the old `web/services/leprinceos.py` functions (preserve quirks: Now Showing / Calendar title = primary film's title; Coming Soon / Classics title = `display_title or primary film title`; `genre` always `""`). This is a pure data-source swap.
- No caching. Local ORM queries only; always reflect the current DB. Do NOT import `requests` in the new module.
- `today` = `timezone.localdate()` (America/New_York). Showtime local date/time via `starts_at.astimezone(CINEMA_TZ)` (`Showtime.starts_at` is an aware datetime, not a string).
- `get_calendar_month(year, month)` keeps `month` **0-based** (0 = January).
- Do NOT change templates, views' bodies, the `cinema` models, the dashboard, or the `import_leprinceos` command. Only `web/services/cinema_data.py` (new), `web/views.py` (import line), and web tests change; `web/services/leprinceos.py` + `web/tests/test_leprinceos.py` are deleted.
- `test_pages.py`/`test_e2e.py` patch `web.views.<fn>` (the views namespace) — they keep working after the import swap and must NOT be edited.
- Tests: `python manage.py test web`. Run from repo root with `source .venv/bin/activate`.

---

### Task 1: Module foundation + `get_now_showing`

**Files:**
- Create: `web/services/cinema_data.py`
- Create: `web/tests/test_cinema_data.py`

**Interfaces:**
- Produces: `web.services.cinema_data.CINEMA_TZ`; helpers `_format_showtime(dt)`, `_local_date(dt)`, `_format_runtime(minutes)`; `get_now_showing() -> list[dict]` with keys `id,title,rating,runtime,genre,poster,showtimes,youtube_id,is_free_for_members` (showtimes = `{date_iso: [time_str,...]}`).

- [ ] **Step 1: Write the failing test**

Create `web/tests/test_cinema_data.py`:

```python
import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.test import TestCase
from django.utils import timezone

from web.services.cinema_data import (
    CINEMA_TZ,
    _format_runtime,
    get_now_showing,
)


def make_screen():
    return Screen.objects.create(name="Screen 1", capacity=100)


def make_film(title="Dune", **kw):
    return Film.objects.create(title=title, **kw)


def make_engagement(screen, films, *, start, end, status="CONFIRMED", kind="REGULAR",
                    show=True, event_title=""):
    eng = Engagement.objects.create(
        screen=screen, start_date=start, end_date=end, status=status, kind=kind,
        show_in_main_listings=show, event_title=event_title,
    )
    for i, f in enumerate(films, start=1):
        EngagementFilm.objects.create(engagement=eng, film=f, position=i)
    return eng


def aware(y, mo, d, hh, mm=0):
    return timezone.make_aware(datetime.datetime(y, mo, d, hh, mm))


class FormatRuntimeTests(TestCase):
    def test_format(self) -> None:
        self.assertEqual(_format_runtime(None), "")
        self.assertEqual(_format_runtime(0), "")
        self.assertEqual(_format_runtime(40), "40min")
        self.assertEqual(_format_runtime(60), "1h")
        self.assertEqual(_format_runtime(100), "1h 40min")


class NowShowingTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.film = make_film("Dune", runtime_minutes=155, rating="PG-13",
                              poster_url="http://p/d.jpg", youtube_id="yt1")
        self.today = timezone.localdate()

    def test_active_engagement_grouped_by_date(self) -> None:
        eng = make_engagement(self.screen, [self.film],
                              start=self.today, end=self.today + datetime.timedelta(days=3))
        d = self.today
        Showtime.objects.create(engagement=eng, starts_at=aware(d.year, d.month, d.day, 13, 0))
        Showtime.objects.create(engagement=eng, starts_at=aware(d.year, d.month, d.day, 19, 0))
        d2 = self.today + datetime.timedelta(days=1)
        Showtime.objects.create(engagement=eng, starts_at=aware(d2.year, d2.month, d2.day, 19, 0))
        out = get_now_showing()
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertEqual(m["title"], "Dune")
        self.assertEqual(m["rating"], "PG-13")
        self.assertEqual(m["runtime"], "2h 35min")
        self.assertEqual(m["genre"], "")
        self.assertEqual(m["poster"], "http://p/d.jpg")
        self.assertEqual(m["youtube_id"], "yt1")
        self.assertEqual(sorted(m["showtimes"].keys()), [d.isoformat(), d2.isoformat()])
        self.assertEqual(m["showtimes"][d.isoformat()], ["1:00 PM", "7:00 PM"])

    def test_hidden_engagement_excluded(self) -> None:
        eng = make_engagement(self.screen, [self.film],
                              start=self.today, end=self.today + datetime.timedelta(days=3), show=False)
        Showtime.objects.create(engagement=eng, starts_at=aware(self.today.year, self.today.month, self.today.day, 19, 0))
        self.assertEqual(get_now_showing(), [])

    def test_out_of_window_excluded(self) -> None:
        far = self.today + datetime.timedelta(days=30)
        eng = make_engagement(self.screen, [self.film], start=far, end=far + datetime.timedelta(days=2))
        Showtime.objects.create(engagement=eng, starts_at=aware(far.year, far.month, far.day, 19, 0))
        self.assertEqual(get_now_showing(), [])

    def test_only_cancelled_showtimes_dropped(self) -> None:
        eng = make_engagement(self.screen, [self.film],
                              start=self.today, end=self.today + datetime.timedelta(days=3))
        Showtime.objects.create(engagement=eng,
                                starts_at=aware(self.today.year, self.today.month, self.today.day, 19, 0),
                                is_cancelled=True)
        self.assertEqual(get_now_showing(), [])

    def test_free_for_members_flag(self) -> None:
        eng = make_engagement(self.screen, [self.film],
                              start=self.today, end=self.today + datetime.timedelta(days=3),
                              kind="CLASSIC")  # CLASSIC is free for members
        Showtime.objects.create(engagement=eng, starts_at=aware(self.today.year, self.today.month, self.today.day, 19, 0))
        out = get_now_showing()
        self.assertTrue(out[0]["is_free_for_members"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test web.tests.test_cinema_data -v 2`
Expected: FAIL — `web.services.cinema_data` missing.

- [ ] **Step 3: Create the module + `get_now_showing`**

Create `web/services/cinema_data.py`:

```python
"""Public-site cinema data, served from the native `cinema` ORM tables.

Reproduces the return shapes of the retired web/services/leprinceos.py (which
fetched the leprinceos HTTP API) so web/views.py and the templates are
unchanged. No request-time cache — reads the DB directly."""

import calendar
import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from cinema.models import Engagement, Showtime

CINEMA_TZ = ZoneInfo("America/New_York")


def _format_showtime(dt):
    # e.g. "6:00 PM" — strip the leading zero on the hour.
    return dt.astimezone(CINEMA_TZ).strftime("%I:%M %p").lstrip("0")


def _local_date(dt):
    return dt.astimezone(CINEMA_TZ).date()


def _format_runtime(minutes):
    if not minutes:
        return ""
    h, m = divmod(int(minutes), 60)
    if h == 0:
        return f"{m}min"
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}min"


def get_now_showing():
    """Confirmed, visible engagements active in the next 7 days, each with its
    non-cancelled showtimes grouped by local date. Only movies with at least
    one upcoming showtime date. Matches the old API-backed shape."""
    today = timezone.localdate()
    week_out = today + datetime.timedelta(days=7)

    engagements = (
        Engagement.objects.filter(
            status="CONFIRMED", start_date__lte=week_out, end_date__gte=today,
        )
        .exclude(show_in_main_listings=False)
        .prefetch_related("engagement_films__film")
    )

    movies = []
    for engagement in engagements:
        pf = engagement.primary_film
        showtimes_by_date = {}
        for st in engagement.showtimes.filter(is_cancelled=False):
            local_date = _local_date(st.starts_at).isoformat()
            showtimes_by_date.setdefault(local_date, []).append(
                _format_showtime(st.starts_at)
            )
        if not showtimes_by_date:
            continue
        movies.append(
            {
                "id": str(engagement.id),
                "title": pf.title if pf else "",
                "rating": (pf.rating if pf else "") or "",
                "runtime": _format_runtime(pf.runtime_minutes if pf else None),
                "genre": "",
                "poster": (pf.poster_url if pf else "") or "",
                "showtimes": showtimes_by_date,
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "is_free_for_members": bool(engagement.is_free_for_members),
            }
        )
    return movies
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test web.tests.test_cinema_data -v 2`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add web/services/cinema_data.py web/tests/test_cinema_data.py
git commit -m "feat(web): cinema_data.get_now_showing from the ORM"
```

---

### Task 2: `get_coming_soon`

**Files:**
- Modify: `web/services/cinema_data.py`
- Modify: `web/tests/test_cinema_data.py`

**Interfaces:**
- Consumes: the module + helpers from Task 1.
- Produces: `get_coming_soon() -> list[dict]` with keys `id,title,start_date,release_date,genre,poster,films,description,youtube_id,is_free_for_members` (films = list of `{id,title,poster}`).

- [ ] **Step 1: Write the failing test**

Append to `web/tests/test_cinema_data.py`:

```python
from web.services.cinema_data import get_coming_soon


class ComingSoonTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.today = timezone.localdate()
        self.a = make_film("Alpha", runtime_minutes=90, synopsis="a-syn",
                           poster_url="http://p/a.jpg", youtube_id="yta")
        self.b = make_film("Beta", runtime_minutes=100, poster_url="http://p/b.jpg")

    def _future(self, films, days=3, **kw):
        s = self.today + datetime.timedelta(days=days)
        return make_engagement(self.screen, films, start=s, end=s + datetime.timedelta(days=2), **kw)

    def test_future_non_classic_returned(self) -> None:
        self._future([self.a])
        out = get_coming_soon()
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertEqual(m["title"], "Alpha")
        self.assertEqual(m["genre"], "")
        self.assertEqual(m["poster"], "http://p/a.jpg")
        self.assertEqual(m["description"], "a-syn")
        self.assertEqual(m["youtube_id"], "yta")
        self.assertEqual(m["films"], [{"id": self.a.id, "title": "Alpha", "poster": "http://p/a.jpg"}])
        self.assertEqual(m["start_date"], (self.today + datetime.timedelta(days=3)).isoformat())

    def test_classic_excluded(self) -> None:
        self._future([self.a], kind="CLASSIC")
        self.assertEqual(get_coming_soon(), [])

    def test_dedup_by_film_set(self) -> None:
        self._future([self.a], days=3)
        self._future([self.a], days=5)   # same film -> deduped
        self._future([self.a, self.b], days=6, kind="DOUBLE_FEATURE")  # distinct set -> kept
        titles = sorted(m["title"] for m in get_coming_soon())
        self.assertEqual(len(get_coming_soon()), 2)

    def test_release_date_format(self) -> None:
        s = self.today + datetime.timedelta(days=3)
        self._future([self.a], days=3)
        expected = s.strftime("%B %-d")
        self.assertEqual(get_coming_soon()[0]["release_date"], expected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test web.tests.test_cinema_data.ComingSoonTests -v 2`
Expected: FAIL — `get_coming_soon` not defined.

- [ ] **Step 3: Implement `get_coming_soon`**

Append to `web/services/cinema_data.py`:

```python
def get_coming_soon():
    """Confirmed engagements starting tomorrow+, non-CLASSIC, deduped by film
    set (a double feature is a distinct set)."""
    today = timezone.localdate()
    tomorrow = today + datetime.timedelta(days=1)

    engagements = (
        Engagement.objects.filter(status="CONFIRMED", start_date__gte=tomorrow)
        .exclude(kind="CLASSIC")
        .prefetch_related("engagement_films__film")
        .order_by("start_date")
    )

    seen = set()
    movies = []
    for engagement in engagements:
        films = engagement.ordered_films
        ids = sorted(f.id for f in films)
        key = ",".join(str(i) for i in ids) if ids else engagement.display_title
        if key in seen:
            continue
        seen.add(key)

        pf = engagement.primary_film
        movies.append(
            {
                "id": str(engagement.id),
                "title": engagement.display_title or (pf.title if pf else ""),
                "start_date": engagement.start_date.isoformat(),
                "release_date": engagement.start_date.strftime("%B %-d"),
                "genre": "",
                "poster": (pf.poster_url if pf else "") or "",
                "films": [
                    {"id": f.id, "title": f.title, "poster": f.poster_url} for f in films
                ],
                "description": (pf.synopsis if pf else "") or "",
                "youtube_id": (pf.youtube_id if pf else "") or "",
                "is_free_for_members": bool(engagement.is_free_for_members),
            }
        )
    return movies
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test web.tests.test_cinema_data.ComingSoonTests -v 2`
Expected: PASS (4 tests). Then `python manage.py test web.tests.test_cinema_data` → green.

- [ ] **Step 5: Commit**

```bash
git add web/services/cinema_data.py web/tests/test_cinema_data.py
git commit -m "feat(web): cinema_data.get_coming_soon from the ORM"
```

---

### Task 3: `get_calendar_month`

**Files:**
- Modify: `web/services/cinema_data.py`
- Modify: `web/tests/test_cinema_data.py`

**Interfaces:**
- Consumes: the module from Tasks 1–2.
- Produces: `get_calendar_month(year, month) -> dict[int, list[dict]]` (`month` 0-based); each value item = `{id,title,poster,youtube_id}`.

- [ ] **Step 1: Write the failing test**

Append to `web/tests/test_cinema_data.py`:

```python
from web.services.cinema_data import get_calendar_month


class CalendarMonthTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.film = make_film("Dune", poster_url="http://p/d.jpg", youtube_id="yt1")
        self.eng = make_engagement(self.screen, [self.film],
                                   start=datetime.date(2026, 6, 1), end=datetime.date(2026, 6, 30))

    def test_groups_by_local_day(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 4, 13, 0))
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 4, 19, 0))  # same day, dedup by title
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 10, 19, 0))
        data = get_calendar_month(2026, 5)  # month 5 == June (0-based)
        self.assertEqual(sorted(data.keys()), [4, 10])
        self.assertEqual(len(data[4]), 1)  # deduped per day by title
        self.assertEqual(data[4][0]["title"], "Dune")
        self.assertEqual(data[4][0]["poster"], "http://p/d.jpg")
        self.assertEqual(data[4][0]["youtube_id"], "yt1")

    def test_late_night_local_day(self) -> None:
        # 23:00 local on the 15th stays on the 15th (not the 16th UTC)
        Showtime.objects.create(engagement=self.eng, starts_at=aware(2026, 6, 15, 23, 0))
        data = get_calendar_month(2026, 5)
        self.assertIn(15, data)

    def test_empty_month(self) -> None:
        self.assertEqual(get_calendar_month(2026, 0), {})  # January, no showtimes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test web.tests.test_cinema_data.CalendarMonthTests -v 2`
Expected: FAIL — `get_calendar_month` not defined.

- [ ] **Step 3: Implement `get_calendar_month`**

Append to `web/services/cinema_data.py`:

```python
def get_calendar_month(year, month):
    """Non-cancelled showtimes whose local day falls in the month, grouped by
    day-of-month (int), deduped per day by title. `month` is 0-based (0=Jan).
    Returns {} for an empty month."""
    cal_month = month + 1
    last_day = calendar.monthrange(year, cal_month)[1]
    start = timezone.make_aware(datetime.datetime(year, cal_month, 1, 0, 0, 0))
    end = timezone.make_aware(datetime.datetime(year, cal_month, last_day, 23, 59, 59))

    showtimes = (
        Showtime.objects.filter(is_cancelled=False, starts_at__gte=start, starts_at__lte=end)
        .select_related("screen")
        .prefetch_related("engagement__engagement_films__film")
    )

    data = {}
    for st in showtimes:
        day = _local_date(st.starts_at).day
        pf = st.engagement.primary_film
        title = pf.title if pf else ""
        movies = data.setdefault(day, [])
        if any(m["title"] == title for m in movies):
            continue
        movies.append(
            {
                "id": str(st.id),
                "title": title,
                "poster": (pf.poster_url if pf else "") or "",
                "youtube_id": (pf.youtube_id if pf else "") or "",
            }
        )
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test web.tests.test_cinema_data.CalendarMonthTests -v 2`
Expected: PASS (3 tests). Then `python manage.py test web.tests.test_cinema_data` → green.

- [ ] **Step 5: Commit**

```bash
git add web/services/cinema_data.py web/tests/test_cinema_data.py
git commit -m "feat(web): cinema_data.get_calendar_month from the ORM"
```

---

### Task 4: `get_classic_movie_night`

**Files:**
- Modify: `web/services/cinema_data.py`
- Modify: `web/tests/test_cinema_data.py`

**Interfaces:**
- Consumes: the module from Tasks 1–3.
- Produces: `get_classic_movie_night() -> dict` = `{"next_screening": <dict|None>, "upcoming": [<dict>]}`; each screening = `{id,title,poster,rating,runtime,synopsis,youtube_id,date,display_date}`.

- [ ] **Step 1: Write the failing test**

Append to `web/tests/test_cinema_data.py`:

```python
from web.services.cinema_data import get_classic_movie_night


class ClassicMovieNightTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.today = timezone.localdate()
        self.film = make_film("Casablanca", runtime_minutes=102, rating="PG",
                              synopsis="classic-syn", poster_url="http://p/c.jpg", youtube_id="ytc")

    def _classic(self):
        return make_engagement(self.screen, [self.film],
                               start=self.today, end=self.today + datetime.timedelta(days=14),
                               kind="CLASSIC", event_title="Casablanca Night")

    def test_future_screenings_split(self) -> None:
        eng = self._classic()
        d1 = self.today + datetime.timedelta(days=1)
        d2 = self.today + datetime.timedelta(days=8)
        Showtime.objects.create(engagement=eng, starts_at=aware(d2.year, d2.month, d2.day, 19, 0))
        Showtime.objects.create(engagement=eng, starts_at=aware(d1.year, d1.month, d1.day, 19, 0))
        out = get_classic_movie_night()
        self.assertIsNotNone(out["next_screening"])
        self.assertEqual(out["next_screening"]["date"], d1.isoformat())
        self.assertEqual(out["next_screening"]["title"], "Casablanca Night")
        self.assertEqual(out["next_screening"]["rating"], "PG")
        self.assertEqual(out["next_screening"]["runtime"], "1h 42min")
        self.assertEqual(out["next_screening"]["synopsis"], "classic-syn")
        self.assertEqual(len(out["upcoming"]), 1)
        self.assertEqual(out["upcoming"][0]["date"], d2.isoformat())

    def test_past_showtimes_excluded(self) -> None:
        eng = self._classic()
        past = self.today - datetime.timedelta(days=1)
        Showtime.objects.create(engagement=eng, starts_at=aware(past.year, past.month, past.day, 19, 0))
        self.assertEqual(get_classic_movie_night(), {"next_screening": None, "upcoming": []})

    def test_no_classics(self) -> None:
        self.assertEqual(get_classic_movie_night(), {"next_screening": None, "upcoming": []})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test web.tests.test_cinema_data.ClassicMovieNightTests -v 2`
Expected: FAIL — `get_classic_movie_night` not defined.

- [ ] **Step 3: Implement `get_classic_movie_night`**

Append to `web/services/cinema_data.py`:

```python
def get_classic_movie_night():
    """Confirmed CLASSIC engagements still running or upcoming, expanded into
    one screening per non-cancelled future showtime, sorted by date. Returns
    {"next_screening": <dict|None>, "upcoming": [<dict>]}."""
    today = timezone.localdate()
    engagements = (
        Engagement.objects.filter(kind="CLASSIC", status="CONFIRMED", end_date__gte=today)
        .prefetch_related("engagement_films__film")
    )

    screenings = []
    for engagement in engagements:
        pf = engagement.primary_film
        title = engagement.display_title or (pf.title if pf else "")
        for st in engagement.showtimes.filter(is_cancelled=False):
            local = st.starts_at.astimezone(CINEMA_TZ)
            if local.date() < today:
                continue
            screenings.append(
                {
                    "id": str(st.id),
                    "title": title,
                    "poster": (pf.poster_url if pf else "") or "",
                    "rating": (pf.rating if pf else "") or "",
                    "runtime": _format_runtime(pf.runtime_minutes if pf else None),
                    "synopsis": (pf.synopsis if pf else "") or "",
                    "youtube_id": (pf.youtube_id if pf else "") or "",
                    "date": local.date().isoformat(),
                    "display_date": local.strftime("%A, %B %-d"),
                }
            )

    screenings.sort(key=lambda s: s["date"])
    return {
        "next_screening": screenings[0] if screenings else None,
        "upcoming": screenings[1:],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test web.tests.test_cinema_data.ClassicMovieNightTests -v 2`
Expected: PASS (3 tests). Then `python manage.py test web.tests.test_cinema_data` → green (all four functions).

- [ ] **Step 5: Commit**

```bash
git add web/services/cinema_data.py web/tests/test_cinema_data.py
git commit -m "feat(web): cinema_data.get_classic_movie_night from the ORM"
```

---

### Task 5: Cutover — repoint views, delete the API module

**Files:**
- Modify: `web/views.py` (import line only)
- Delete: `web/services/leprinceos.py`, `web/tests/test_leprinceos.py`

**Interfaces:**
- Consumes: `web.services.cinema_data` (all four functions + `CINEMA_TZ`).

- [ ] **Step 1: Repoint the import in `web/views.py`**

Change the import block (currently `from web.services.leprinceos import (...)`) to source from the new module — same names:

```python
from web.services.cinema_data import (
    CINEMA_TZ,
    get_now_showing,
    get_coming_soon,
    get_calendar_month,
    get_classic_movie_night,
)
```

Leave everything else in `web/views.py` unchanged.

- [ ] **Step 2: Delete the retired API module + its test**

```bash
git rm web/services/leprinceos.py web/tests/test_leprinceos.py
```

- [ ] **Step 3: Run the web suite**

Run: `python manage.py test web -v 1`
Expected: PASS. `test_pages.py`/`test_e2e.py` patch `web.views.<fn>` (the views namespace), so they resolve against the newly-imported names and pass unchanged. No import errors from the deleted module (grep to confirm nothing else references it):

Run: `grep -rn "services.leprinceos\|services import leprinceos" --include=*.py .`
Expected: no matches (only the `import_leprinceos` command remains, which is `cinema/management/...`, unrelated).

- [ ] **Step 4: Commit**

```bash
git add web/views.py
git commit -m "refactor(web): serve public pages from cinema_data (retire leprinceos API module)"
```

---

### Task 6: Final verification + browser smoke

**Files:** none (verification only).

- [ ] **Step 1: System + migration checks**

Run: `python manage.py check` → `System check identified no issues`.
Run: `python manage.py makemigrations --check --dry-run` → `No changes detected` (no model changes).

- [ ] **Step 2: Web + full suite**

Run: `python manage.py test web -v 1` → PASS.
Run: `python manage.py test` → PASS (blog/cinema/dashboard/web, no regressions).

- [ ] **Step 3: Confirm no `requests` in the public data path**

Run: `grep -n "requests" web/services/cinema_data.py`
Expected: no matches (the ORM module makes no HTTP calls).

- [ ] **Step 4: Manual browser smoke (recommended)**

Seed the DB (`python manage.py import_leprinceos --flush`), then `runserver` and open the public home page (`/`): confirm Now Showing (with grouped showtimes + date nav) and Coming Soon render; open the calendar toggle + month nav; open `/classics` for the classic-night screening list. Then edit an engagement in the dashboard (e.g. flip its status or add a showtime) and reload the public page — the change appears immediately (no cache lag). Compare against the previous API-backed look (should be identical).

---

## Self-Review

**Spec coverage:**
- `cinema_data.py` (CINEMA_TZ + helpers) + `get_now_showing` → Task 1. ✅
- `get_coming_soon` (dedup by film set, non-CLASSIC) → Task 2. ✅
- `get_calendar_month` (0-based month, local-day grouping, per-day title dedup) → Task 3. ✅
- `get_classic_movie_night` (future screenings, next+upcoming split) → Task 4. ✅
- Repoint `web/views.py` import; delete `leprinceos.py` + `test_leprinceos.py`; `test_pages`/`test_e2e` untouched → Task 5. ✅
- No caching / no `requests` in the module; verification + browser smoke → Tasks 1–6. ✅
- Out-of-scope items (templates, models, dashboard, import command, LEPRINCEOS_BASE_URL) → untouched. ✅

**Placeholder scan:** No vague steps; full function code + tests inlined. Verbatim helper `_format_runtime` preserved.

**Type consistency:** All four function names + return-dict keys match the old `leprinceos.py` shapes (`id,title,rating,runtime,genre,poster,showtimes,youtube_id,is_free_for_members` for now_showing; `id,title,start_date,release_date,genre,poster,films,description,youtube_id,is_free_for_members` for coming_soon; `{day:int -> [{id,title,poster,youtube_id}]}` for calendar; `{next_screening,upcoming}` with `id,title,poster,rating,runtime,synopsis,youtube_id,date,display_date` screenings for classics), so `web/views.py` + templates need no changes. `CINEMA_TZ`, `_format_showtime(dt)`, `_local_date(dt)`, `_format_runtime(minutes)` consistent across tasks. `_local_date` returns a `date` (calendar uses `.day`, now_showing uses `.isoformat()`) — used consistently. Helpers take aware `datetime` (not strings) since `Showtime.starts_at` is aware.
