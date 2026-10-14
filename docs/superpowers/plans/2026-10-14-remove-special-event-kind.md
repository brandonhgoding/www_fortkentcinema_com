# Remove the Special Event Kind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop `Engagement.Kind.SPECIAL_EVENT`, rename `event_title` to `display_title`, and park the Heckle Night lineup until the Event model lands.

**Architecture:** Heckle Night is unhooked first, while the kind still exists, so the suite stays green at every commit. The model change then lands as one commit: two migrations, the field rename, the fallback property renamed to `title`, and every reader of the old property moved over. The dashboard loses the kind option and relabels the field last.

**Tech Stack:** Django 5.2, SQLite locally, htmx + Alpine dashboard, `manage.py test` + `flake8`.

**Spec:** `docs/superpowers/specs/2026-10-14-remove-special-event-kind-design.md`

## Global Constraints

- Tests: `.venv/bin/python manage.py test <label> -v 2`. Full suite: `.venv/bin/python manage.py test`. Lint: `.venv/bin/flake8`.
- Work on a branch `feat/remove-special-event`. Commit per task; do not merge or push unless asked.
- `show_in_main_listings` is not touched anywhere.
- `web/services/titles.py` is not touched.
- Historical specs under `docs/superpowers/specs/` are not edited.
- Migration numbering: `cinema` is at `0024_remove_sponsorship`. New ones are `0025` and `0026`.

## Review Focus

1. A row with `kind="SPECIAL_EVENT"` already in the table when 0026 runs: it must come out `REGULAR` with its title intact (Task 2 migration test).
2. An engagement with no films and no override: `title` must be `""`, not raise (Task 2 model test).
3. A POST to the engagement form with `kind=SPECIAL_EVENT`: rejected with a form error, no row created (Task 3).
4. A Regular engagement with a display title set: the dashboard list and detail show the override, and the detail page shows the "Display title" row (Task 3).
5. Heckle Night with a confirmed, listed, 7:00 PM third-Friday booking of any kind: still "Not booked yet", and the page renders 200 (Task 1).

---

### Task 1: Park the Heckle Night lineup

**Files:**
- Modify: `web/services/heckle_night.py` (module docstring lines 1-37, `heckle_showtimes` lines 88-161, `get_heckle_nights` line 176)
- Modify: `web/constants.py:500-515` (the `start_time` comment)
- Test: `web/tests/test_heckle_night.py:150-291`

**Interfaces:**
- Produces: `heckle_showtimes(dates) -> dict` returning `{}` always. `get_heckle_nights` signature unchanged; every row has `film=None`.

- [ ] **Step 1: Rewrite the lineup tests**

In `HeckleLineupTests` (the class whose `book` helper starts at line 150):

- Change `book`'s default to `kind=Engagement.Kind.REGULAR` and reword its docstring to "A 7:00 PM booking on the night. `kind` is still a parameter because the interim lookup must refuse every kind."
- Delete `test_booked_night_carries_its_film`, `test_seven_oclock_on_the_nose_is`, `test_a_special_event_is`, `test_the_regular_feature_does_not_win_over_the_event`.
- Replace them with one test:

```python
def test_nothing_is_claimed_until_the_event_model_lands(self):
    """Interim: the lineup lookup is parked. A perfect booking — confirmed,
    listed, 7:00 PM on the night, any kind — still reads "Not booked yet"."""
    for kind in Engagement.Kind.values:
        with self.subTest(kind=kind):
            Engagement.objects.all().delete()
            self.book("Plan 9 From Outer Space", self.night, kind=kind)
            self.assertIsNone(self.nights()[0]["film"])
```

- In `test_no_other_kind_counts_either`, keep the loop but change the docstring to one line: "Every other kind is refused too; see the interim note on heckle_showtimes."
- In `test_query_count_does_not_grow_with_the_number_of_nights`, change both `assertNumQueries(3)` to `assertNumQueries(0)`.
- Leave `test_unbooked_night_still_appears`, `test_only_a_seven_oclock_event_is_heckle_night`, `test_cancelled_showtime_is_not_a_lineup`, `test_draft_engagement_is_not_a_lineup`, `test_showtime_on_another_day_is_ignored`, `test_the_regular_friday_feature_is_not_heckle_night`, `test_a_private_event_is_still_not_advertised` as they are.
- In `web/tests/test_event_titles.py`, delete `test_heckle_page_drops_the_suffix` (the page no longer shows a film) and drop the now-unused `get_heckle_nights` import. The other two tests in that class stay.

- [ ] **Step 2: Run the tests to see the new one and the query count fail**

Run: `.venv/bin/python manage.py test web.tests.test_heckle_night -v 2`
Expected: `test_nothing_is_claimed_until_the_event_model_lands` fails on the SPECIAL_EVENT subtest; `test_query_count_does_not_grow_with_the_number_of_nights` fails with 3 queries where 0 were expected.

- [ ] **Step 3: Park `heckle_showtimes`**

In `web/services/heckle_night.py`, replace the body of `heckle_showtimes(dates)` with `return {}` and this docstring:

> Interim: always empty. The lineup used to match the 7:00 PM Special Event on each date, and that kind no longer exists. The Event model replaces this lookup; until it lands every night reads "Not booked yet".

Remove the now-unused imports (`Engagement`, `Showtime`, `_local_date`, `HECKLE_NIGHT` if nothing else in the module uses it; `upcoming_nights` still uses `HECKLE_NIGHT`). In the module docstring, replace the paragraph beginning "Where it DIVERGES from craft night" through "...what would replace it." with two sentences: the film lookup is parked until the Event model exists, and the dates still compute. Leave `get_heckle_nights` as is for now; `engagement.display_title` on line 176 is renamed in Task 2.

In `web/constants.py`, in the `start_time` comment, delete the sentence "the same trade the SPECIAL_EVENT filter makes" through "a migration nobody needs yet." and keep the rest.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python manage.py test web.tests.test_heckle_night web.tests.test_event_titles -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/services/heckle_night.py web/constants.py web/tests/test_heckle_night.py web/tests/test_event_titles.py
git commit -m "feat(heckle-night): park the lineup lookup until the Event model lands"
```

---

### Task 2: Model, migrations, and the title rename

**Files:**
- Modify: `cinema/models/engagement.py:68-78, 151-156, 194-196`
- Create: `cinema/migrations/0025_special_event_to_regular.py`
- Create: `cinema/migrations/0026_remove_special_event_rename_display_title.py`
- Modify (property readers, `.display_title` becomes `.title`): `boxoffice/sync.py:57,358,362,366`, `boxoffice/spec.py:33`, `cinema/admin.py:30`, `cinema/models/showtime.py:58`, `cinema/showtimes_overlap.py:67`, `cinema/social_cards/card.py:139`, `dashboard/smart_alerts.py:39`, `dashboard/views.py:554,596,659`, `dashboard/templates/dashboard/_social_cards.html:18`, `dashboard/templates/dashboard/_engagement_list.html:13,28,43,61`, `dashboard/templates/dashboard/engagement_detail.html:3,10,19,21`, `dashboard/templates/dashboard/home.html:56,73`, `phone/speech.py:55`, `web/services/cinema_data.py:153,163`, `web/services/heckle_night.py:176`
- Modify (field readers, `event_title` becomes `display_title`): `dashboard/forms.py:61,65`, `dashboard/templates/dashboard/_engagement_form.html:44`, `dashboard/templates/dashboard/engagement_detail.html:48-49`, `cinema/social_cards/draw.py:58` (comment only)
- Test: `cinema/tests/test_models.py`, new `cinema/tests/test_migrations.py`, plus fixture renames in `boxoffice/tests/test_spec.py`, `boxoffice/tests/test_sync.py`, `cinema/tests/test_social_cards_card.py`, `dashboard/tests/test_smart_alerts.py`, `dashboard/tests/test_engagements.py`, `dashboard/tests/test_square_views.py`, `web/tests/test_cinema_data.py`, `web/tests/test_event_titles.py`

**Interfaces:**
- Produces: `Engagement.display_title: CharField(max_length=200, blank=True)`; `Engagement.title -> str` property (override or `" + ".join(film titles)`, `""` with neither); `Engagement.Kind` = `REGULAR`, `CLASSIC`, `DOUBLE_FEATURE`; migration module function `special_event_to_regular(apps, schema_editor) -> None`.
- Consumes: Task 1's `heckle_night.py` (one rename on line 176).

- [ ] **Step 1: Write the model tests**

In `cinema/tests/test_models.py`, `EngagementTestCase`:

- Rename `test_display_title_from_films_in_position_order` to `test_title_from_films_in_position_order` and assert `eng.title == "Alpha + Beta"`.
- Replace `test_event_title_overrides_display_title` with:

```python
def test_display_title_overrides_the_film_titles(self) -> None:
    eng = self._engagement(display_title="Summer Double Feature")
    self.assertEqual(eng.title, "Summer Double Feature")

def test_title_is_empty_with_no_films_and_no_override(self) -> None:
    self.assertEqual(self._engagement().title, "")

def test_special_event_is_no_longer_a_kind(self) -> None:
    self.assertEqual(
        Engagement.Kind.values, ["REGULAR", "CLASSIC", "DOUBLE_FEATURE"]
    )
    self.assertFalse(hasattr(Engagement, "default_visibility_for"))
```

- [ ] **Step 2: Write the migration test**

Create `cinema/tests/test_migrations.py`. A plain `TestCase`, not the executor: choices are not enforced by the database, so a `SPECIAL_EVENT` row can be created against the final schema and the data function run on it directly. This avoids a `TransactionTestCase` flush, which would wipe the seeded audience catalogue other tests rely on (see the docstring of `audience/tests/test_membership_term_migration.py`).

```python
import datetime
from importlib import import_module

from cinema.models import Engagement, Screen
from django.apps import apps
from django.test import TestCase

MIGRATION = import_module("cinema.migrations.0025_special_event_to_regular")
NIGHT = datetime.date(2026, 10, 16)


class SpecialEventToRegularTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="S", capacity=10)

    def _row(self, kind, title=""):
        return Engagement.objects.create(
            screen=self.screen, start_date=NIGHT, end_date=NIGHT,
            kind=kind, display_title=title,
        )

    def test_special_event_rows_become_regular_and_keep_their_title(self) -> None:
        event = self._row("SPECIAL_EVENT", "Heckle Night")
        classic = self._row("CLASSIC", "Noir Night")
        MIGRATION.special_event_to_regular(apps, None)
        event.refresh_from_db()
        classic.refresh_from_db()
        self.assertEqual((event.kind, event.display_title), ("REGULAR", "Heckle Night"))
        self.assertEqual((classic.kind, classic.display_title), ("CLASSIC", "Noir Night"))
```

- [ ] **Step 3: Run both to verify they fail**

Run: `.venv/bin/python manage.py test cinema.tests.test_models cinema.tests.test_migrations -v 2`
Expected: `test_migrations` fails at import (no module `0025_special_event_to_regular`); the model tests fail with `TypeError: unexpected keyword 'display_title'` and `AttributeError: 'Engagement' object has no attribute 'title'`.

- [ ] **Step 4: Write migration 0025**

`cinema/migrations/0025_special_event_to_regular.py`, depending on `("cinema", "0024_remove_sponsorship")`. Module-level `special_event_to_regular(apps, schema_editor)` does `apps.get_model("cinema", "Engagement").objects.filter(kind="SPECIAL_EVENT").update(kind="REGULAR")`. One operation: `migrations.RunPython(special_event_to_regular, migrations.RunPython.noop)`. A two-line comment says the reverse is a no-op because nothing can tell which Regular rows were events.

- [ ] **Step 5: Change the model**

In `cinema/models/engagement.py`:

- Remove `SPECIAL_EVENT` from `Kind`.
- Rename the field: `display_title = models.CharField(max_length=200, blank=True)`.
- Rename the property `display_title` to `title`; body reads `self.display_title` first, else the join.
- `__str__` uses `self.title`.
- Delete `default_visibility_for`.

- [ ] **Step 6: Generate migration 0026**

Run: `.venv/bin/python manage.py makemigrations cinema -n remove_special_event_rename_display_title`
Expected: one new file with `AlterField` on `kind` and `RenameField` from `event_title` to `display_title`. If `makemigrations` asks whether the field was renamed, answer yes. Open the file and confirm it depends on `0025_special_event_to_regular`, and that there is no `RemoveField` + `AddField` pair (that would drop the data).

- [ ] **Step 7: Move every reader**

Mechanical, in the files listed above: each `.display_title` property read becomes `.title`, and each `event_title` field reference becomes `display_title`. Two spots need a word changed, not just a name:

- `cinema/admin.py:30`: `list_display` entry becomes `"title"`.
- `dashboard/templates/dashboard/engagement_detail.html:48-49`: the condition becomes `{% if engagement.display_title %}` (the old inequality could never be true, since the override *is* the title when set) and the label becomes `Display title:`. The form template's label on line 44 is changed in Task 3; here only rename `form.event_title` to `form.display_title`.

Then update the test fixtures: every `event_title=` keyword, `"event_title"` payload key, and `.event_title =` assignment becomes `display_title`; every `.display_title` assertion on the old property becomes `.title` (`web/tests/test_event_titles.py:104` reads `.title`; the test name at `boxoffice/tests/test_spec.py:29` can stay). The `book` helper default at `web/tests/test_event_titles.py:73` becomes `kind=Engagement.Kind.REGULAR`, since a default argument is evaluated at import and the member no longer exists. Grep to confirm nothing is left:

Run: `grep -rn "event_title\|SPECIAL_EVENT" --include='*.py' --include='*.html' boxoffice cinema dashboard phone web | grep -v migrations`
Expected: no output.

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/python manage.py test`
Expected: PASS. Then `.venv/bin/python manage.py makemigrations --check --dry-run` prints "No changes detected".

- [ ] **Step 9: Commit**

```bash
git add -A cinema boxoffice dashboard phone web
git commit -m "feat(cinema): drop the Special Event kind, rename event_title to display_title"
```

---

### Task 3: Dashboard loses the kind and relabels the field

**Files:**
- Modify: `dashboard/forms.py:50-51` (`KIND_OPTIONS`), `dashboard/views.py:254-255` (`KIND_LABELS`)
- Modify: `dashboard/templates/dashboard/_engagement_form.html:43-45`
- Test: `dashboard/tests/test_engagements.py`

**Interfaces:**
- Consumes: Task 2's `display_title` field and `title` property.

- [ ] **Step 1: Write the tests**

In `dashboard/tests/test_engagements.py`, in the class that owns `_payload` (line 167):

```python
def test_special_event_is_rejected(self) -> None:
    resp = self.client.post(reverse("dashboard:engagement_create"),
                            self._payload(kind="SPECIAL_EVENT"))
    self.assertEqual(Engagement.objects.count(), 0)
    self.assertContains(resp, "Select a valid choice")

def test_display_title_is_offered_for_a_regular_run(self) -> None:
    html = self.client.get(reverse("dashboard:engagement_create")).content.decode()
    self.assertNotIn("SPECIAL_EVENT", html)
    self.assertIn("Display title", html)
    self.assertNotIn('x-show="kind !== \'REGULAR\'"', html)

def test_display_title_shows_on_the_detail_page(self) -> None:
    e = make_engagement(self.screen, start=self.today, end=self.today,
                        films=[self.f1], display_title="Noir Night")
    html = self.client.get(reverse("dashboard:engagement_detail", args=[e.pk])).content.decode()
    self.assertIn("Display title", html)
    self.assertIn("Noir Night", html)
```

(`make_engagement` is the module helper at line 12; if the detail URL name differs, use the one `dashboard/tests/test_engagement_detail.py` uses.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_engagements -v 2`
Expected: `test_special_event_is_rejected` fails because the row is created; `test_display_title_is_offered_for_a_regular_run` fails on the `SPECIAL_EVENT` option and the "Event title" label; the detail test passes already if Task 2 relabelled the row, which is fine.

- [ ] **Step 3: Implement**

- `dashboard/forms.py`: drop the `("SPECIAL_EVENT", "Special Event")` tuple from `KIND_OPTIONS`.
- `dashboard/views.py`: drop `"SPECIAL_EVENT": "Event"` from `KIND_LABELS`.
- `_engagement_form.html`: remove the `<div x-show="kind !== 'REGULAR'">` wrapper and render `{% field form.display_title label="Display title" %}` directly after the film picker group.

- [ ] **Step 4: Run the dashboard tests**

Run: `.venv/bin/python manage.py test dashboard -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard
git commit -m "feat(dashboard): drop Special Event from the engagement form, relabel display title"
```

---

### Task 4: Lint, full suite, and the tidy-up

**Files:**
- Modify: `cinema/social_cards/draw.py:58` (comment says `event_title`), any flake8 findings

- [ ] **Step 1: Lint**

Run: `.venv/bin/flake8`
Expected: clean. Unused imports left behind in `web/services/heckle_night.py` are the likely finding.

- [ ] **Step 2: Fix the stray comment**

In `cinema/social_cards/draw.py:58`, change `event_title` to `display_title`.

- [ ] **Step 3: Full suite and migration check**

Run: `.venv/bin/python manage.py test && .venv/bin/python manage.py makemigrations --check --dry-run`
Expected: all tests pass; "No changes detected".

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: lint and comment tidy after Special Event removal"
```
