# Backfill Past Films Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A re-runnable Django management command that seeds `Film` / `Engagement` / `Showtime` records for ~2 years of past Fort Kent Cinema runs (embedded from Square sales data) so they appear on the public calendar, enriched with TMDB metadata.

**Architecture:** One management command, `cinema/management/commands/backfill_past_films.py`, modeled on `link_film_reviews`. The 90-film dataset is embedded as a module-level `FILMS` list. Pure helpers (`engagement_kind`, `daterange`, `find_free_slot`) are unit-tested in isolation; `handle()` orchestrates skip-detection, TMDB resolution, engagement/showtime creation, and conflict-free showtime placement, tested end-to-end via `call_command` with a mocked `TMDBService`.

**Tech Stack:** Django 5, Django `TestCase`, `unittest.mock`, existing `cinema.services.import_film_from_tmdb` and `cinema.tmdb.services.TMDBService`.

## Global Constraints

- Python interpreter is `.venv/bin/python`; run Django via `.venv/bin/python manage.py …`.
- Tests run with `.venv/bin/python manage.py test cinema` (Django `TestCase`, not pytest).
- `settings.TIME_ZONE = "America/New_York"`, `USE_TZ = True`. Build local-time showtimes with `django.utils.timezone.make_aware(datetime(...))` — the default tz is already `America/New_York`, so no explicit `ZoneInfo` is needed.
- `Showtime` has `UniqueConstraint(screen, starts_at)` — placement logic must never emit two showtimes for the same `(screen, starts_at)`.
- Engagement kinds are `Engagement.Kind.REGULAR / SPECIAL_EVENT / CLASSIC / DOUBLE_FEATURE`. Visibility helper: `Engagement.default_visibility_for(kind)` returns `True` only for `REGULAR`.
- Reuse `import_film_from_tmdb(tmdb_id, service=…)` (in `cinema/services.py`) to create/reuse films by `tmdb_id` — do not re-implement TMDB film creation.
- Every `git commit` message ends with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Command scaffold, embedded data, and pure helpers

**Files:**
- Create: `cinema/management/commands/backfill_past_films.py`
- Test: `cinema/tests/test_backfill_past_films.py`

**Interfaces:**
- Consumes: `Engagement.Kind` (from `cinema.models`).
- Produces:
  - `FILMS: list[dict]` — module constant; each dict has keys `title, type, startDate, endDate, daysWithSales, ticketsSold, notes`.
  - `engagement_kind(entry: dict) -> str` — returns an `Engagement.Kind` value.
  - `daterange(start: datetime.date, end: datetime.date) -> Iterator[date]` — inclusive of both ends.

- [ ] **Step 1: Generate the embedded `FILMS` literal from the source JSON**

The source dataset is `/Users/bgoding/Desktop/fort_kent_cinema_films.json` (present on the dev machine; will NOT exist on prod, which is why we embed it). Produce the Python literal deterministically:

Run:
```bash
cd /Users/bgoding/code/SoftwareMaine/www_fortkentcinema_com
.venv/bin/python -c "import json,pprint; d=json.load(open('/Users/bgoding/Desktop/fort_kent_cinema_films.json')); print(len(d['films'])); pprint.pprint(d['films'][0])"
```
Expected: prints `90` then the first film dict:
```
{'daysWithSales': 24,
 'endDate': '2024-07-25',
 'notes': '',
 'startDate': '2024-06-18',
 'ticketsSold': 472,
 'title': 'Despicable Me 4',
 'type': 'Film'}
```

- [ ] **Step 2: Write the command module with the embedded data and pure helpers**

Create `cinema/management/commands/backfill_past_films.py`. Paste the **full** 90-element list produced from the JSON `films` array as `FILMS` (generate it with the one-liner below and paste its stdout verbatim in place of the `# … 90 dicts …` marker):

```bash
.venv/bin/python -c "import json; d=json.load(open('/Users/bgoding/Desktop/fort_kent_cinema_films.json')); print('FILMS = ' + __import__('pprint').pformat(d['films'], width=100, sort_dicts=True))"
```

```python
"""Backfill past films from Square sales data into cinema tables.

Two years of runs (title + type + start/end date) are embedded below as FILMS.
For each run we ensure a Film exists (enriched from TMDB where possible), create a
CONFIRMED Engagement spanning the dates, and add a 3pm showtime for every calendar
date in the run so the film appears on the public calendar.

Idempotent: a film that already has an engagement is skipped, so re-running never
duplicates. Safe to run on prod: `python manage.py backfill_past_films`.
Use --dry-run first to preview TMDB matches without writing.
"""

import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from cinema.services import import_film_from_tmdb
from cinema.tmdb.services import TMDBService
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

# Preferred showtime is 3pm local; fall back to later hours only when both
# screens are already booked at an earlier hour that day.
SHOWTIME_HOURS = [15, 16, 17, 18, 19, 20, 21, 22]

# FILMS = [ ... 90 dicts, pasted from the one-liner above ... ]


def engagement_kind(entry: dict) -> str:
    """Map a dataset entry to an Engagement kind.

    Regular films -> REGULAR. "Special screening" entries -> SPECIAL_EVENT when
    the note mentions an event, otherwise CLASSIC (re-releases).
    """
    if entry["type"] == "Film":
        return Engagement.Kind.REGULAR
    notes = (entry.get("notes") or "").lower()
    if "event" in notes:
        return Engagement.Kind.SPECIAL_EVENT
    return Engagement.Kind.CLASSIC


def daterange(start: date, end: date) -> Iterator[date]:
    """Yield every date from start to end inclusive."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)
```

- [ ] **Step 3: Write failing tests for the pure helpers**

Create `cinema/tests/test_backfill_past_films.py`:

```python
from datetime import date

from cinema.management.commands import backfill_past_films as cmd
from cinema.models import Engagement
from django.test import TestCase


class HelperTests(TestCase):
    def test_regular_film_kind(self) -> None:
        entry = {"type": "Film", "notes": ""}
        self.assertEqual(cmd.engagement_kind(entry), Engagement.Kind.REGULAR)

    def test_special_classic_kind(self) -> None:
        entry = {"type": "Special screening", "notes": "Classic re-release"}
        self.assertEqual(cmd.engagement_kind(entry), Engagement.Kind.CLASSIC)

    def test_special_event_kind(self) -> None:
        entry = {"type": "Special screening", "notes": "Interactive event screening"}
        self.assertEqual(cmd.engagement_kind(entry), Engagement.Kind.SPECIAL_EVENT)

    def test_daterange_is_inclusive(self) -> None:
        days = list(cmd.daterange(date(2024, 1, 1), date(2024, 1, 3)))
        self.assertEqual(days, [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)])

    def test_films_dataset_loaded(self) -> None:
        self.assertEqual(len(cmd.FILMS), 90)
        self.assertEqual(cmd.FILMS[0]["title"], "Despicable Me 4")
```

- [ ] **Step 4: Run helper tests — expect PASS**

Run: `.venv/bin/python manage.py test cinema.tests.test_backfill_past_films.HelperTests -v 2`
Expected: 5 tests PASS. (If `test_films_dataset_loaded` fails, the `FILMS` literal was not pasted correctly in Step 2.)

- [ ] **Step 5: Commit**

```bash
git add cinema/management/commands/backfill_past_films.py cinema/tests/test_backfill_past_films.py
git commit -m "feat(cinema): backfill_past_films scaffold with embedded data and helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Conflict-free showtime placement

**Files:**
- Modify: `cinema/management/commands/backfill_past_films.py`
- Test: `cinema/tests/test_backfill_past_films.py`

**Interfaces:**
- Consumes: `SHOWTIME_HOURS`, `Screen` (from `cinema.models`).
- Produces:
  - `find_free_slot(taken: set[tuple[int, datetime]], day: date, screens: list[Screen], preferred_index: int) -> tuple[Screen, datetime]` — returns the first free `(screen, aware_datetime)` for that day, trying 3pm on the preferred screen, then 3pm on the other screen, then 4pm on both, etc. Rotates which screen is preferred by `preferred_index`. Raises `RuntimeError` only if every screen×hour combination is taken (not expected in practice).

- [ ] **Step 1: Write the failing test**

Add to `cinema/tests/test_backfill_past_films.py`:

```python
from datetime import datetime

from cinema.management.commands import backfill_past_films as cmd
from cinema.models import Screen
from django.utils import timezone


class FindFreeSlotTests(TestCase):
    def setUp(self) -> None:
        self.a = Screen.objects.create(name="The Century", capacity=1)
        self.b = Screen.objects.create(name="The Savoy", capacity=1)
        self.screens = [self.a, self.b]

    def _at(self, hour: int) -> datetime:
        return timezone.make_aware(datetime(2024, 1, 1, hour, 0))

    def test_prefers_3pm_on_preferred_screen(self) -> None:
        screen, when = cmd.find_free_slot(set(), date(2024, 1, 1), self.screens, 0)
        self.assertEqual(screen, self.a)
        self.assertEqual(when, self._at(15))

    def test_rotates_preferred_screen(self) -> None:
        screen, when = cmd.find_free_slot(set(), date(2024, 1, 1), self.screens, 1)
        self.assertEqual(screen, self.b)
        self.assertEqual(when, self._at(15))

    def test_falls_back_to_other_screen_at_same_hour(self) -> None:
        taken = {(self.a.id, self._at(15))}
        screen, when = cmd.find_free_slot(taken, date(2024, 1, 1), self.screens, 0)
        self.assertEqual(screen, self.b)
        self.assertEqual(when, self._at(15))

    def test_falls_back_to_later_hour_when_both_screens_taken(self) -> None:
        taken = {(self.a.id, self._at(15)), (self.b.id, self._at(15))}
        screen, when = cmd.find_free_slot(taken, date(2024, 1, 1), self.screens, 0)
        self.assertEqual(screen, self.a)
        self.assertEqual(when, self._at(16))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python manage.py test cinema.tests.test_backfill_past_films.FindFreeSlotTests -v 2`
Expected: FAIL with `AttributeError: module 'cinema...backfill_past_films' has no attribute 'find_free_slot'`.

- [ ] **Step 3: Implement `find_free_slot`**

Add to `cinema/management/commands/backfill_past_films.py` (after `daterange`):

```python
def find_free_slot(
    taken: set[tuple[int, datetime]],
    day: date,
    screens: list[Screen],
    preferred_index: int,
) -> tuple[Screen, datetime]:
    """First free (screen, datetime) for `day`, respecting unique(screen, starts_at).

    Tries the preferred hour on every screen before moving to the next hour, so
    concurrent runs spread across both screens at 3pm before anything slides later.
    `taken` holds (screen_id, aware_datetime) pairs already in use; equal instants
    compare equal across time zones, so preloaded UTC values match local candidates.
    """
    ordered = screens[preferred_index % len(screens):] + screens[: preferred_index % len(screens)]
    for hour in SHOWTIME_HOURS:
        when = timezone.make_aware(datetime(day.year, day.month, day.day, hour, 0))
        for screen in ordered:
            if (screen.id, when) not in taken:
                return screen, when
    raise RuntimeError(f"No free showtime slot for {day} across {len(screens)} screens")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python manage.py test cinema.tests.test_backfill_past_films.FindFreeSlotTests -v 2`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cinema/management/commands/backfill_past_films.py cinema/tests/test_backfill_past_films.py
git commit -m "feat(cinema): conflict-free showtime slot placement for backfill

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `handle()` orchestration — skip / create / title-only / dry-run

**Files:**
- Modify: `cinema/management/commands/backfill_past_films.py`
- Test: `cinema/tests/test_backfill_past_films.py`

**Interfaces:**
- Consumes: `FILMS`, `engagement_kind`, `daterange`, `find_free_slot`, `import_film_from_tmdb`, `TMDBService`, `Film`, `Engagement`, `EngagementFilm`, `Showtime`, `Screen`.
- Produces: a `Command(BaseCommand)` class runnable via `call_command("backfill_past_films", dry_run=…, sleep=…)`.

- [ ] **Step 1: Write the failing integration tests**

Add to `cinema/tests/test_backfill_past_films.py`:

```python
from unittest import mock

from cinema.models import Engagement, EngagementFilm, Film, Showtime
from django.core.management import call_command

TMDB_DETAILS = {
    "tmdb_id": 555, "title": "Newish Movie", "release_date": "2024-06-01",
    "overview": "o", "poster_path": "https://img/p.jpg", "backdrop_path": "https://img/b.jpg",
    "runtime": 100, "genres": ["Action"], "imdb_id": "tt555",
}


def _entry(**over):
    base = {
        "title": "Newish Movie", "type": "Film",
        "startDate": "2024-06-01", "endDate": "2024-06-03",
        "daysWithSales": 3, "ticketsSold": 10, "notes": "",
    }
    base.update(over)
    return base


class BackfillHandleTests(TestCase):
    def setUp(self) -> None:
        self.a = Screen.objects.create(name="The Century", capacity=1)
        self.b = Screen.objects.create(name="The Savoy", capacity=1)

    def _mock_service(self, search_results=None, details=TMDB_DETAILS):
        svc = mock.Mock()
        svc.search_films.return_value = (
            [{"tmdb_id": 555, "title": "Newish Movie", "release_date": "2024-06-01"}]
            if search_results is None else search_results
        )
        svc.get_film_details.return_value = details
        return svc

    def _run(self, films, svc, **opts):
        with mock.patch.object(cmd, "FILMS", films), \
             mock.patch.object(cmd, "TMDBService", return_value=svc), \
             mock.patch.object(cmd.time, "sleep"):
            call_command("backfill_past_films", **opts)

    def test_creates_film_engagement_and_showtimes(self) -> None:
        svc = self._mock_service()
        self._run([_entry()], svc)
        film = Film.objects.get(tmdb_id="555")
        eng = Engagement.objects.get()
        self.assertEqual(eng.status, "CONFIRMED")
        self.assertEqual(eng.kind, Engagement.Kind.REGULAR)
        self.assertTrue(eng.show_in_main_listings)
        self.assertEqual(list(eng.films.all()), [film])
        self.assertEqual(Showtime.objects.count(), 3)  # one per date
        for st in Showtime.objects.all():
            self.assertEqual(st.starts_at.astimezone(timezone.get_current_timezone()).hour, 15)

    def test_skips_film_with_existing_engagement(self) -> None:
        film = Film.objects.create(title="Newish Movie")
        eng = Engagement.objects.create(screen=self.a, start_date=date(2024, 6, 1), end_date=date(2024, 6, 3))
        EngagementFilm.objects.create(engagement=eng, film=film, position=1)
        svc = self._mock_service()
        self._run([_entry()], svc)
        svc.search_films.assert_not_called()
        self.assertEqual(Engagement.objects.count(), 1)  # no new engagement
        self.assertEqual(Film.objects.count(), 1)

    def test_title_only_when_no_tmdb_match(self) -> None:
        svc = self._mock_service(search_results=[])
        self._run([_entry(title="Classic Movie (various)")], svc)
        film = Film.objects.get(title="Classic Movie (various)")
        self.assertIsNone(film.tmdb_id)
        self.assertEqual(film.engagements.count(), 1)

    def test_special_screening_is_classic_and_hidden(self) -> None:
        svc = self._mock_service()
        self._run([_entry(type="Special screening", notes="Classic re-release")], svc)
        eng = Engagement.objects.get()
        self.assertEqual(eng.kind, Engagement.Kind.CLASSIC)
        self.assertFalse(eng.show_in_main_listings)

    def test_overlapping_runs_do_not_collide(self) -> None:
        svc = self._mock_service()
        one = _entry(title="Film One")
        two = _entry(title="Film Two")
        two_svc = self._mock_service(
            search_results=[{"tmdb_id": 777, "title": "Film Two", "release_date": "2024-06-01"}],
            details={**TMDB_DETAILS, "tmdb_id": 777, "imdb_id": "tt777", "title": "Film Two"},
        )
        # first film -> tmdb 555, second -> 777; same dates, must not clash
        def search(title, *a, **k):
            return ([{"tmdb_id": 777, "title": "Film Two", "release_date": "2024-06-01"}]
                    if title == "Film Two"
                    else [{"tmdb_id": 555, "title": "Film One", "release_date": "2024-06-01"}])
        def details(tmdb_id, *a, **k):
            return {**TMDB_DETAILS, "tmdb_id": tmdb_id, "imdb_id": f"tt{tmdb_id}",
                    "title": "Film Two" if tmdb_id == 777 else "Film One"}
        svc.search_films.side_effect = search
        svc.get_film_details.side_effect = details
        self._run([one, two], svc)
        self.assertEqual(Showtime.objects.count(), 6)  # 3 + 3, no collisions
        # each date has both screens used once at 15:00
        first_day = [s for s in Showtime.objects.all()
                     if s.starts_at.astimezone(timezone.get_current_timezone()).date() == date(2024, 6, 1)]
        self.assertEqual({s.screen_id for s in first_day}, {self.a.id, self.b.id})

    def test_dry_run_writes_nothing(self) -> None:
        svc = self._mock_service()
        self._run([_entry()], svc, dry_run=True)
        self.assertEqual(Film.objects.count(), 0)
        self.assertEqual(Engagement.objects.count(), 0)
        self.assertEqual(Showtime.objects.count(), 0)
        svc.search_films.assert_called_once()  # still looks up to preview the match
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test cinema.tests.test_backfill_past_films.BackfillHandleTests -v 2`
Expected: FAIL (the command has no `add_arguments`/`handle`; `call_command` errors or no records are created).

- [ ] **Step 3: Implement `add_arguments` and `handle`**

Append to `cinema/management/commands/backfill_past_films.py`:

```python
def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


class Command(BaseCommand):
    help = "Backfill past films (embedded Square data) into cinema tables for the calendar."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Look up TMDB matches but write nothing to the database.",
        )
        parser.add_argument(
            "--sleep", type=float, default=1.0,
            help="Seconds to pause between TMDB lookups (default 1.0).",
        )

    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]
        sleep_s: float = options["sleep"]

        screens = list(Screen.objects.order_by("id"))
        if not screens:
            raise CommandError("No screens configured; create screens before backfilling.")

        taken: set[tuple[int, datetime]] = set(
            Showtime.objects.values_list("screen_id", "starts_at")
        )
        service = TMDBService()

        created = skipped = title_only = showtimes_made = 0
        title_only_names: list[str] = []

        for index, entry in enumerate(FILMS):
            title = entry["title"]

            # 1. Cheap skip: an existing film with this title/slug that already runs.
            slug = slugify(title)
            if Film.objects.filter(
                Q(title__iexact=title) | Q(slug=slug), engagements__isnull=False
            ).exists():
                self.stdout.write(f"SKIP     {title} (already has engagements)")
                skipped += 1
                continue

            # 2. Resolve via TMDB.
            results = service.search_films(title)
            time.sleep(sleep_s)

            if results:
                top = results[0]
                self.stdout.write(
                    f"MATCH    {title} -> {top.get('title')} "
                    f"({(top.get('release_date') or '????')[:4]}) tmdb:{top.get('tmdb_id')}"
                )
                if dry_run:
                    existing = Film.objects.filter(tmdb_id=str(top["tmdb_id"])).first()
                    if existing and existing.engagements.exists():
                        self.stdout.write(f"SKIP     {title} (already has engagements)")
                        skipped += 1
                    else:
                        created += 1
                    continue
                film = import_film_from_tmdb(int(top["tmdb_id"]), service=service)
                if film.engagements.exists():
                    self.stdout.write(f"SKIP     {title} (already has engagements)")
                    skipped += 1
                    continue
            else:
                self.stdout.write(f"NO-TMDB  {title} (creating title-only)")
                title_only += 1
                title_only_names.append(title)
                if dry_run:
                    continue
                film = Film.objects.create(title=title)

            # 4/5. Engagement + conflict-free showtimes.
            start, end = _parse(entry["startDate"]), _parse(entry["endDate"])
            kind = engagement_kind(entry)

            slots = []
            for day in daterange(start, end):
                screen, when = find_free_slot(taken, day, screens, index)
                taken.add((screen.id, when))
                slots.append((screen, when))

            note = (entry.get("notes") or "").strip()
            eng_notes = "Backfilled from Square sales data"
            if note:
                eng_notes = f"{note}\n{eng_notes}"

            with transaction.atomic():
                engagement = Engagement.objects.create(
                    screen=slots[0][0] if slots else screens[0],
                    start_date=start,
                    end_date=end,
                    kind=kind,
                    status="CONFIRMED",
                    show_in_main_listings=Engagement.default_visibility_for(kind),
                    notes=eng_notes,
                )
                EngagementFilm.objects.create(engagement=engagement, film=film, position=1)
                for screen, when in slots:
                    try:
                        Showtime.objects.create(engagement=engagement, screen=screen, starts_at=when)
                        showtimes_made += 1
                    except IntegrityError:
                        # Backstop only; find_free_slot should prevent this.
                        continue

            self.stdout.write(self.style.SUCCESS(f"CREATED  {title} ({start} -> {end}, {len(slots)} showtimes)"))
            if results:
                created += 1

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(
            f"\n{verb}: {created}  Skipped: {skipped}  "
            f"Title-only: {title_only}  Showtimes: {showtimes_made}"
        ))
        if title_only_names:
            self.stdout.write("\nTitle-only films to enrich by hand in admin:")
            for name in title_only_names:
                self.stdout.write(f"  - {name}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test cinema.tests.test_backfill_past_films.BackfillHandleTests -v 2`
Expected: 6 tests PASS.

- [ ] **Step 5: Run the whole cinema suite**

Run: `.venv/bin/python manage.py test cinema -v 1`
Expected: all pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add cinema/management/commands/backfill_past_films.py cinema/tests/test_backfill_past_films.py
git commit -m "feat(cinema): backfill_past_films handle() with TMDB, skip, and dry-run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Local dry-run smoke test against the real dataset

**Files:** none (verification only).

- [ ] **Step 1: Preview all 90 films without writing**

Run: `.venv/bin/python manage.py backfill_past_films --dry-run --sleep 0`
Expected: 90 lines of `MATCH` / `SKIP` / `NO-TMDB`, then a summary. `Film`, `Engagement`, and `Showtime` counts unchanged afterward (verify with a shell one-liner):

```bash
.venv/bin/python manage.py shell -c "from cinema.models import Film, Engagement, Showtime; print(Film.objects.count(), Engagement.objects.count(), Showtime.objects.count())"
```
Expected: same counts as before the dry run (66 films / 46 engagements / whatever showtimes existed).

- [ ] **Step 2: Eyeball the TMDB matches**

Read the `MATCH` lines for the known-tricky titles and confirm the matched title/year is sane:
- `Snow White` (Square typo note) — should match the 2025 Disney film, not the 1937 one if the year is off; note any mismatch for manual fixing later.
- `Star Wars` (re-release) — top hit may be a different cut; acceptable, will fix in admin.
- `Moana (Live Action)`, `Quintuplets (Nov 4)`, `Classic Movie (various)` — likely `NO-TMDB` / title-only; confirm they appear in the title-only list.

This is an eyeball check, not an assertion — the command already handles all outcomes. Report anything that looks wrong to the user rather than "fixing" it in code.

## Self-Review

**Spec coverage:**
- Embedded data, no `--file` → Task 1 (`FILMS`). ✓
- `--dry-run` / `--sleep` (default 1.0) → Task 3 `add_arguments`. ✓
- Cheap skip check before TMDB → Task 3 step 3 (title/slug + `engagements__isnull=False`). ✓
- TMDB resolve via `import_film_from_tmdb`, re-check engagements → Task 3. ✓
- Title-only fallback + summary list → Task 3 (`title_only_names`). ✓
- Kind mapping (REGULAR / CLASSIC / SPECIAL_EVENT) + `default_visibility_for` → Task 1 helper + Task 3. ✓
- `status=CONFIRMED`, backfill note marker → Task 3. ✓
- Conflict-free 3pm placement respecting `unique(screen, starts_at)`, preloaded taken set, IntegrityError backstop → Task 2 + Task 3. ✓
- Idempotency → covered by skip check; verified by `test_skips_film_with_existing_engagement`. ✓
- Output lines + summary → Task 3. ✓
- Tests 1–6 from spec → Task 1/2/3 test methods map 1:1 (skip, create+showtimes, title-only, conflict, kind, dry-run). ✓

**Placeholder scan:** The only intentional marker is the `# FILMS = [...]` comment in Task 1, which Step 1/Step 2 fill deterministically from the source JSON via the given one-liner — reproducible, not a TODO. Task 3 Step 3 flags and then removes its own scaffolding assignment lines. No other placeholders.

**Type consistency:** `find_free_slot(taken, day, screens, preferred_index)` signature identical in Task 2 definition and Task 3 call site. `engagement_kind(entry)` returns `Engagement.Kind` values used directly as `kind=`. `daterange(start, end)` yields `date`. `taken` is `set[tuple[int, datetime]]` throughout. `import_film_from_tmdb(int(tmdb_id), service=service)` matches the existing `cinema/services.py` signature.
