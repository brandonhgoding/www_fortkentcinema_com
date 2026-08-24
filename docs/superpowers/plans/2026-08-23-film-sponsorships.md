# Film Sponsorships Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let local businesses browse Universal's bookable catalog at `/sponsor/` and inquire about underwriting a screening, with an importer that loads studio DCP lists.

**Architecture:** `Studio` and `StudioTitle` join `Film` in the `cinema` app but stay separate from it — `Film` remains "films we have actually shown", `StudioTitle` is "titles a studio will rent us". A `--studio`-parameterized management command imports studio spreadsheets idempotently. The public page is a plain Django `ListView` with querystring filtering and pagination — no JS. Inquiries persist to the database and surface in the dashboard, because this project has no mail backend.

**Tech Stack:** Django 5.2, openpyxl (new dependency), esbuild CSS bundling via `frontend/`, SQLite in dev / Postgres in prod. No JS framework — the site has no Alpine, no htmx on public pages, and this feature adds none.

**Spec:** `docs/superpowers/specs/2026-08-23-film-sponsorships-design.md`

## Global Constraints

- **Python line length: 88** (`.flake8` `max-line-length = 88`, `extend-ignore = E203, W503`). Migrations are excluded from flake8.
- **Verification gates that actually run here: `flake8` and `python manage.py test`.** mypy cannot run in this project and black is configured but unapplied — do not claim either as verification.
- **There is no `python` on PATH.** Use `.venv/bin/python` for every command in this plan.
- **Public CSS is bundled.** Never add a `<link>` tag to `templates/base.html`. Add the stylesheet to `static/css/` **and** register it in `frontend/styles/main.css` in cascade order (pages group, last), then run `npm run build` from `frontend/`.
- **Dashboard CSS is per-page.** Dashboard templates link their own stylesheet in `{% block head_extra %}` — the opposite of the public site.
- **Django's `{# #}` comment is single-line only.** Multi-line comments in templates must use `{% comment %}`; a multi-line `{# #}` leaks as literal page text and `web/tests/test_pages.py` guards against it.
- **Prices are `$299 / $499 / $799`** for Presenting Sponsor / Community Screening / Full House. Tier 3 copy must state **"first 100 guests"** and **"medium, butter included"**.
- **A.H. Custom Carpentry sponsoring *The Wild Robot*** is a real, approved example and may be named in public copy.
- **`is_available` and `hidden_reason` are never overwritten by a re-import.** Hiding a title must survive the next catalog drop.
- **The importer must be idempotent.** Running it twice changes nothing the second time.
- Section pages keep a trailing slash (`/sponsor/`); action endpoints do not (`/sponsor/inquire`), matching `/vote/cast`.

---

### Task 1: Title and runtime parsing helpers

Pure functions, no Django, no database. Isolated here because the spreadsheet's
messiness is the riskiest part of this feature and deserves its own test cycle.

**Files:**
- Create: `cinema/studio_catalog.py`
- Create: `cinema/tests/test_studio_catalog.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `normalize_title(raw: str) -> str`
  - `parse_runtime(value: object) -> tuple[int | None, str]` returning `(minutes, raw_string)`
  - `clean_cell(value: object) -> str`

- [ ] **Step 1: Write the failing tests**

Create `cinema/tests/test_studio_catalog.py`:

```python
from cinema.studio_catalog import clean_cell, normalize_title, parse_runtime
from django.test import SimpleTestCase


class NormalizeTitleTests(SimpleTestCase):
    def test_moves_trailing_article_to_front(self):
        self.assertEqual(normalize_title("BAD GUYS 2, THE"), "The Bad Guys 2")
        self.assertEqual(normalize_title("MAN WHO LAUGHS, THE"), "The Man Who Laughs")
        self.assertEqual(normalize_title("355, THE"), "The 355")

    def test_keeps_small_words_lowercase_inside_title(self):
        self.assertEqual(
            normalize_title("SECRET LIFE OF PETS, THE"),
            "The Secret Life of Pets",
        )
        self.assertEqual(
            normalize_title("20,000 LEAGUES UNDER THE SEA"),
            "20,000 Leagues Under the Sea",
        )

    def test_does_not_split_at_apostrophes(self):
        # str.title() would produce "Freddy'S" here.
        self.assertEqual(
            normalize_title("FIVE NIGHTS AT FREDDY'S 2"),
            "Five Nights at Freddy's 2",
        )
        self.assertEqual(normalize_title("HONEY, DON'T!"), "Honey, Don't!")

    def test_capitalizes_after_a_colon(self):
        self.assertEqual(
            normalize_title("GABBY'S DOLLHOUSE: THE MOVIE"),
            "Gabby's Dollhouse: The Movie",
        )

    def test_hyphenated_words_are_each_capitalized(self):
        self.assertEqual(
            normalize_title("40-YEAR-OLD VIRGIN, THE"),
            "The 40-Year-Old Virgin",
        )

    def test_year_parenthetical_is_preserved(self):
        self.assertEqual(normalize_title("SCARFACE (1932)"), "Scarface (1932)")
        self.assertEqual(normalize_title("9 (2009)"), "9 (2009)")

    def test_already_cased_parenthetical_is_left_alone(self):
        self.assertEqual(
            normalize_title("2 FAST 2 FURIOUS (aka Fast & Furious 2)"),
            "2 Fast 2 Furious (aka Fast & Furious 2)",
        )

    def test_numeric_title_survives(self):
        self.assertEqual(normalize_title("1917"), "1917")

    def test_empty_input(self):
        self.assertEqual(normalize_title(""), "")
        self.assertEqual(normalize_title(None), "")


class ParseRuntimeTests(SimpleTestCase):
    def test_integer_passes_through_with_no_raw(self):
        self.assertEqual(parse_runtime(132), (132, ""))

    def test_takes_leading_number_and_keeps_raw(self):
        self.assertEqual(parse_runtime("119 & 146"), (119, "119 & 146"))
        self.assertEqual(parse_runtime("93 & 95"), (93, "93 & 95"))

    def test_handles_embedded_newline_and_short_note(self):
        self.assertEqual(
            parse_runtime("94\n(incl 5min short)"),
            (94, "94\n(incl 5min short)"),
        )
        self.assertEqual(
            parse_runtime("91 (inc. 4 min. short)"),
            (91, "91 (inc. 4 min. short)"),
        )

    def test_unparseable_returns_none_but_keeps_raw(self):
        self.assertEqual(parse_runtime("unknown"), (None, "unknown"))

    def test_none_is_empty(self):
        self.assertEqual(parse_runtime(None), (None, ""))


class CleanCellTests(SimpleTestCase):
    def test_none_becomes_empty_string(self):
        self.assertEqual(clean_cell(None), "")

    def test_float_drops_trailing_zero(self):
        # openpyxl reads the AUDIO column as 5.1 (float) and 1 (int).
        self.assertEqual(clean_cell(5.1), "5.1")
        self.assertEqual(clean_cell(1.0), "1")

    def test_string_is_stripped(self):
        self.assertEqual(clean_cell("  5.1, 7.1, Atmos  "), "5.1, 7.1, Atmos")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python manage.py test cinema.tests.test_studio_catalog -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'cinema.studio_catalog'`

- [ ] **Step 3: Write the implementation**

Create `cinema/studio_catalog.py`:

```python
"""Parsing helpers for studio DCP availability spreadsheets.

Studio lists are typed by hand and read like it: titles are shouted in caps
with the article moved to the end ("BAD GUYS 2, THE"), runtimes are sometimes
two numbers ("119 & 146") or carry a note about an attached short, and the
audio column arrives from openpyxl as an int, a float, or a string depending
on the row.

These functions are pure so the awkward cases can be tested without a
spreadsheet or a database.
"""

import re

_ARTICLES = ("THE", "A", "AN")

# Lowercased inside a title, but never as the first or last word, and never
# straight after a colon.
_SMALL_WORDS = frozenset(
    {
        "a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
        "nor", "of", "on", "or", "the", "to", "vs", "with",
    }
)

_TRAILING_PAREN = re.compile(r"\s*(\([^()]*\))\s*$")
_LEADING_INT = re.compile(r"\s*(\d+)")


def clean_cell(value: object) -> str:
    """Stringify a spreadsheet cell without float artifacts.

    openpyxl gives the AUDIO column as 1 (int), 5.1 (float), or
    "5.1, 7.1, Atmos" (str). `str(1.0)` would render "1.0"; `:g` gives "1".
    """
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value).strip()


def _titlecase(text: str) -> str:
    """Title-case whole words, so apostrophes and hyphens survive.

    `str.title()` splits on every non-alpha character and renders
    "FREDDY'S" as "Freddy'S". This walks tokens instead.
    """
    tokens = re.split(r"(\s+|-)", text)
    words = [t for t in tokens if t.strip() and t != "-"]
    total = len(words)

    out: list[str] = []
    index = 0
    previous = ""
    for token in tokens:
        if not token.strip() or token == "-":
            out.append(token)
            continue
        lowered = token.lower()
        edge = index in (0, total - 1)
        after_colon = previous.endswith(":")
        if lowered in _SMALL_WORDS and not edge and not after_colon:
            out.append(lowered)
        else:
            out.append(lowered[:1].upper() + lowered[1:])
        previous = token
        index += 1
    return "".join(out)


def normalize_title(raw: object) -> str:
    """Turn a studio's shouted title into something printable.

    "BAD GUYS 2, THE" -> "The Bad Guys 2"
    """
    text = (str(raw) if raw is not None else "").strip()
    if not text:
        return ""

    paren = ""
    match = _TRAILING_PAREN.search(text)
    if match:
        paren = match.group(1)
        text = text[: match.start()].strip()

    for article in _ARTICLES:
        suffix = f", {article}"
        if text.upper().endswith(suffix):
            text = f"{article} {text[: -len(suffix)].strip()}"
            break

    result = _titlecase(text)

    if paren:
        inner = paren[1:-1]
        # "(aka Fast & Furious 2)" is already cased by hand; "(1932)" is not.
        if any(char.islower() for char in inner):
            result = f"{result} {paren}"
        else:
            result = f"{result} ({_titlecase(inner)})"
    return result


def parse_runtime(value: object) -> tuple[int | None, str]:
    """Return (minutes, original_string).

    The original is kept whenever it carried more than a number, so
    "119 & 146" is not silently reduced to 119 on the page.
    """
    if value is None:
        return None, ""
    if isinstance(value, int) and not isinstance(value, bool):
        return value, ""
    raw = str(value).strip()
    match = _LEADING_INT.match(raw)
    return (int(match.group(1)) if match else None), raw
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python manage.py test cinema.tests.test_studio_catalog -v 2`
Expected: PASS (all tests)

- [ ] **Step 5: Lint**

Run: `.venv/bin/python -m flake8 cinema/studio_catalog.py cinema/tests/test_studio_catalog.py`
Expected: no output

- [ ] **Step 6: Commit**

```bash
git add cinema/studio_catalog.py cinema/tests/test_studio_catalog.py
git commit -m "feat(cinema): title and runtime parsing for studio catalogs"
```

---

### Task 2: `Studio` and `StudioTitle` models

**Files:**
- Create: `cinema/models/studio.py`
- Create: `cinema/models/studio_title.py`
- Modify: `cinema/models/__init__.py`
- Modify: `cinema/admin.py`
- Create: `cinema/tests/test_studio_models.py`
- Create: migration via `makemigrations`

**Interfaces:**
- Consumes: `cinema.studio_catalog.clean_cell` (Task 1) — not directly, but the same module.
- Produces:
  - `cinema.models.Studio` — fields `name`, `slug`, `is_active`, `catalog_updated`
  - `cinema.models.StudioTitle` — fields per spec
  - `StudioTitle.objects.available() -> QuerySet[StudioTitle]`
  - `StudioTitle.release_year -> int | None`
  - `StudioTitle.format_summary -> str`

- [ ] **Step 1: Write the failing tests**

Create `cinema/tests/test_studio_models.py`:

```python
import datetime

from cinema.models import Film, Studio, StudioTitle
from django.db import IntegrityError
from django.test import TestCase


class StudioTitleTests(TestCase):
    def setUp(self) -> None:
        self.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )

    def make(self, **kwargs) -> StudioTitle:
        defaults = {
            "studio": self.studio,
            "original_title": "BAD GUYS 2, THE",
            "title": "The Bad Guys 2",
            "release_date": datetime.date(2025, 8, 1),
        }
        defaults.update(kwargs)
        return StudioTitle.objects.create(**defaults)

    def test_release_year_from_date(self):
        self.assertEqual(self.make().release_year, 2025)

    def test_release_year_is_none_without_a_date(self):
        self.assertIsNone(self.make(release_date=None).release_year)

    def test_format_summary_joins_non_empty_parts(self):
        title = self.make(
            aspect_ratio="Scope", audio="5.1, 7.1, Atmos", notes="4K"
        )
        self.assertEqual(title.format_summary, "Scope · 5.1, 7.1, Atmos · 4K")

    def test_format_summary_skips_blanks(self):
        self.assertEqual(self.make(aspect_ratio="Scope").format_summary, "Scope")
        self.assertEqual(self.make(original_title="X").format_summary, "")

    def test_available_excludes_hidden_titles(self):
        self.make()
        self.make(original_title="HIDDEN", title="Hidden", is_available=False)
        self.assertEqual(
            [t.title for t in StudioTitle.objects.available()], ["The Bad Guys 2"]
        )

    def test_available_excludes_inactive_studios(self):
        self.make()
        other = Studio.objects.create(name="Gone", slug="gone", is_active=False)
        StudioTitle.objects.create(
            studio=other, original_title="X", title="X"
        )
        self.assertEqual(
            [t.title for t in StudioTitle.objects.available()], ["The Bad Guys 2"]
        )

    def test_natural_key_is_unique(self):
        self.make()
        with self.assertRaises(IntegrityError):
            self.make()

    def test_same_title_different_release_date_is_allowed(self):
        # Dracula (1931) really does ship under two release dates.
        self.make(original_title="DRACULA", release_date=datetime.date(1931, 2, 13))
        self.make(original_title="DRACULA", release_date=datetime.date(1931, 4, 24))
        self.assertEqual(
            StudioTitle.objects.filter(original_title="DRACULA").count(), 2
        )

    def test_film_link_is_optional_and_survives_film_deletion(self):
        film = Film.objects.create(title="The Bad Guys 2")
        title = self.make(film=film)
        film.delete()
        title.refresh_from_db()
        self.assertIsNone(title.film)

    def test_str_is_the_display_title(self):
        self.assertEqual(str(self.make()), "The Bad Guys 2")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python manage.py test cinema.tests.test_studio_models -v 2`
Expected: FAIL — `ImportError: cannot import name 'Studio' from 'cinema.models'`

- [ ] **Step 3: Write the models**

Create `cinema/models/studio.py`:

```python
from django.db import models


class Studio(models.Model):
    """A distributor whose availability list we have imported.

    `is_active=False` pulls a studio's whole catalog off the sponsor page in
    one move — when a licensing arrangement lapses or a list goes stale —
    without touching the per-title `is_available` flags underneath it.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    catalog_updated = models.DateField(
        null=True,
        blank=True,
        help_text="Revision date printed on the studio's own list.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
```

Create `cinema/models/studio_title.py`:

```python
from typing import ClassVar

from django.db import models


class StudioTitleQuerySet(models.QuerySet):
    def available(self) -> "StudioTitleQuerySet":
        return self.filter(is_available=True, studio__is_active=True)


class StudioTitle(models.Model):
    """A title a studio will rent us — not a film we have shown.

    Deliberately separate from `Film`. `Film` is the site catalog: every row
    there has a slug, a /movies/<slug> page and a place in the sitemap. This
    table holds ~1,140 Universal titles we have never screened, of which only
    five overlap with `Film`, and it carries exhibition metadata (aspect
    ratio, audio formats, DCP notes) that `Film` has nowhere to put.

    The `film` FK is populated opportunistically for that handful of
    overlaps and is never required.
    """

    # as_manager() returns a Manager that forwards .available() to the
    # queryset, so both StudioTitle.objects.available() and
    # some_queryset.available() work.
    objects: ClassVar[models.Manager["StudioTitle"]] = (
        StudioTitleQuerySet.as_manager()
    )

    studio = models.ForeignKey(
        "cinema.Studio", on_delete=models.CASCADE, related_name="titles"
    )

    # As the studio wrote it ("BAD GUYS 2, THE"). This is the re-import
    # matching key, so it must never be prettified in place.
    original_title = models.CharField(max_length=200)
    # Normalized for display ("The Bad Guys 2").
    title = models.CharField(max_length=200)

    release_date = models.DateField(null=True, blank=True)
    aspect_ratio = models.CharField(max_length=60, blank=True)
    audio = models.CharField(max_length=60, blank=True)
    mpa_rating = models.CharField(max_length=20, blank=True)

    # Parsed for sorting; `runtime_raw` keeps oddities like "119 & 146" so a
    # two-cut title is not silently reduced to one number.
    runtime_minutes = models.PositiveIntegerField(null=True, blank=True)
    runtime_raw = models.CharField(max_length=60, blank=True)

    notes = models.CharField(max_length=200, blank=True)
    variant_note = models.CharField(
        max_length=300,
        blank=True,
        help_text="Other DCP variants collapsed into this row on import.",
    )

    film = models.ForeignKey(
        "cinema.Film",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="studio_titles",
    )

    # Opt-out: everything a studio lists is sponsorable until we say otherwise.
    is_available = models.BooleanField(default=True)
    hidden_reason = models.CharField(max_length=200, blank=True)

    imported_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "original_title", "release_date"],
                name="unique_studio_title_release",
            )
        ]
        indexes = [
            models.Index(fields=["studio", "is_available"]),
            models.Index(fields=["title"]),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def release_year(self) -> int | None:
        return self.release_date.year if self.release_date else None

    @property
    def format_summary(self) -> str:
        """Exhibition detail folded into one quiet column."""
        parts = [self.aspect_ratio, self.audio, self.notes]
        return " · ".join(part for part in parts if part)
```

Modify `cinema/models/__init__.py` — add the imports and `__all__` entries:

```python
from .studio import Studio
from .studio_title import StudioTitle
```

and add `"Studio"`, `"StudioTitle"` to `__all__`.

- [ ] **Step 4: Register in the admin**

Append to `cinema/admin.py`:

```python
@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "catalog_updated")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(StudioTitle)
class StudioTitleAdmin(admin.ModelAdmin):
    list_display = (
        "title", "studio", "release_date", "mpa_rating",
        "runtime_minutes", "is_available",
    )
    list_filter = ("studio", "is_available", "mpa_rating")
    list_editable = ("is_available",)
    search_fields = ("title", "original_title")
    autocomplete_fields = ("film",)
    readonly_fields = ("imported_at", "updated_at")
```

Add `Studio, StudioTitle` to the existing `from .models import ...` line in
`cinema/admin.py`. `autocomplete_fields = ("film",)` requires `FilmAdmin` to
declare `search_fields`; if it does not, add `search_fields = ("title",)` to it.

- [ ] **Step 5: Make the migration**

```bash
.venv/bin/python manage.py makemigrations cinema
```

Expected: creates `cinema/migrations/00XX_studio_studiotitle.py`

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python manage.py test cinema.tests.test_studio_models -v 2`
Expected: PASS (all tests)

- [ ] **Step 7: Lint and full suite**

```bash
.venv/bin/python -m flake8 cinema/
.venv/bin/python manage.py test cinema -v 1
```
Expected: no flake8 output; all cinema tests pass

- [ ] **Step 8: Commit**

```bash
git add cinema/models/ cinema/admin.py cinema/migrations/ cinema/tests/test_studio_models.py
git commit -m "feat(cinema): Studio and StudioTitle models"
```

---

### Task 3: `import_studio_catalog` management command

**Files:**
- Create: `cinema/management/commands/import_studio_catalog.py`
- Create: `cinema/tests/test_import_studio_catalog.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `Studio`, `StudioTitle` (Task 2); `normalize_title`, `parse_runtime`, `clean_cell` (Task 1).
- Produces: the command `import_studio_catalog --studio <slug> --file <path> [--sheet <name>] [--dry-run]`.

- [ ] **Step 1: Add the dependency**

`openpyxl` is installed in the local venv but absent from `requirements.txt`, so
the command would die with `ModuleNotFoundError` on a fresh checkout or in
production. Append to `requirements.txt`:

```
# Spreadsheet import (studio DCP availability lists)
openpyxl==3.1.5
```

- [ ] **Step 2: Write the failing tests**

Create `cinema/tests/test_import_studio_catalog.py`:

```python
import datetime
import tempfile
from io import StringIO
from pathlib import Path

import openpyxl
from cinema.models import Studio, StudioTitle
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

HEADER = [
    "TITLE", "U.S. RELEASE (YYYY-MM-DD)", "ASPECT RATIO", "AUDIO",
    "MPA RATING", "RUN TIME (MINUTES)", "ADDITIONAL INFORMATION",
]


def workbook(rows, sheet_name="by TITLE") -> str:
    """Write a temp .xlsx shaped like a studio list; return its path."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(HEADER)
    for row in rows:
        ws.append(row)
    path = Path(tempfile.mkdtemp()) / "catalog.xlsx"
    wb.save(path)
    return str(path)


class ImportStudioCatalogTests(TestCase):
    def run_import(self, path, **kwargs):
        out = StringIO()
        call_command(
            "import_studio_catalog",
            studio="universal", file=path, stdout=out, **kwargs
        )
        return out.getvalue()

    def test_creates_studio_and_titles(self):
        path = workbook([
            ["BAD GUYS 2, THE", datetime.datetime(2025, 8, 1),
             "Scope", "5.1, 7.1, Atmos", "PG", 104, "2D & 3D"],
        ])
        self.run_import(path)

        studio = Studio.objects.get(slug="universal")
        self.assertEqual(studio.name, "Universal Pictures")

        title = StudioTitle.objects.get()
        self.assertEqual(title.original_title, "BAD GUYS 2, THE")
        self.assertEqual(title.title, "The Bad Guys 2")
        self.assertEqual(title.release_date, datetime.date(2025, 8, 1))
        self.assertEqual(title.runtime_minutes, 104)
        self.assertEqual(title.notes, "2D & 3D")
        self.assertTrue(title.is_available)

    def test_is_idempotent(self):
        path = workbook([
            ["NOBODY 2", datetime.datetime(2025, 8, 15), "Scope", 5.1, "R", 89, None],
        ])
        self.run_import(path)
        self.run_import(path)
        self.assertEqual(StudioTitle.objects.count(), 1)

    def test_reimport_does_not_resurrect_a_hidden_title(self):
        path = workbook([
            ["NOBODY 2", datetime.datetime(2025, 8, 15), "Scope", 5.1, "R", 89, None],
        ])
        self.run_import(path)
        StudioTitle.objects.update(is_available=False, hidden_reason="too violent")

        self.run_import(path)

        title = StudioTitle.objects.get()
        self.assertFalse(title.is_available)
        self.assertEqual(title.hidden_reason, "too violent")

    def test_collapses_variants_and_records_them(self):
        # Touch of Evil ships as two cuts under one release date.
        path = workbook([
            ["TOUCH OF EVIL", datetime.datetime(1958, 3, 15), "Flat", 1,
             "N/A", 95, "4K Restoration (Original 1958 Theatrical Version)"],
            ["TOUCH OF EVIL", datetime.datetime(1958, 3, 15), "Flat", 1,
             "PG-13", 110, "4K Restoration (1998 Reconstructed Version)"],
        ])
        self.run_import(path)

        title = StudioTitle.objects.get()
        # Longest runtime wins the primary slot.
        self.assertEqual(title.runtime_minutes, 110)
        self.assertIn("95 min", title.variant_note)
        self.assertIn("1958 Theatrical", title.variant_note)

    def test_a_true_duplicate_gets_no_variant_note(self):
        # Notting Hill is listed twice, identically. There is no second
        # version to advertise.
        path = workbook([
            ["NOTTING HILL", datetime.datetime(1999, 5, 28), "Scope", 5.1,
             "PG-13", 124, "2K Restoration"],
            ["NOTTING HILL", datetime.datetime(1999, 5, 28), "Scope", 5.1,
             "PG-13", 124, "2K Restoration"],
        ])
        self.run_import(path)
        self.assertEqual(StudioTitle.objects.get().variant_note, "")

    def test_same_title_different_dates_stay_separate(self):
        path = workbook([
            ["DRACULA", datetime.datetime(1931, 2, 13), "Flat (1.33)", 1,
             "N/A", 75, "2K Restoration"],
            ["DRACULA", datetime.datetime(1931, 4, 24), "Flat (1.33)", 1,
             "N/A", 103, "2K Restoration"],
        ])
        self.run_import(path)
        self.assertEqual(StudioTitle.objects.count(), 2)

    def test_variant_tie_break_is_deterministic(self):
        # Both Dracula 1931-02-13 rows are 75 min and differ only in audio;
        # sheet order decides, so two runs must agree.
        rows = [
            ["DRACULA", datetime.datetime(1931, 2, 13), "Flat (1.33)", 1,
             "N/A", 75, "2K Restoration"],
            ["DRACULA", datetime.datetime(1931, 2, 13), "Flat (1.33)", 5.1,
             "N/A", 75, "2K Restoration"],
        ]
        self.run_import(workbook(rows))
        first = StudioTitle.objects.get().audio
        StudioTitle.objects.all().delete()
        self.run_import(workbook(rows))
        self.assertEqual(StudioTitle.objects.get().audio, first)
        self.assertEqual(first, "1")

    def test_handles_missing_release_date(self):
        path = workbook([
            ["MYSTERY TITLE", None, "Flat", 5.1, "N/A", 90, None],
        ])
        self.run_import(path)
        self.assertIsNone(StudioTitle.objects.get().release_date)

    def test_preserves_awkward_runtime_string(self):
        path = workbook([
            ["1941", datetime.datetime(1979, 12, 14), "Scope", 5.1,
             "PG & N/A", "119 & 146", None],
        ])
        self.run_import(path)
        title = StudioTitle.objects.get()
        self.assertEqual(title.runtime_minutes, 119)
        self.assertEqual(title.runtime_raw, "119 & 146")

    def test_skips_blank_rows(self):
        path = workbook([
            ["NOBODY 2", datetime.datetime(2025, 8, 15), "Scope", 5.1, "R", 89, None],
            [None, None, None, None, None, None, None],
        ])
        self.run_import(path)
        self.assertEqual(StudioTitle.objects.count(), 1)

    def test_dry_run_writes_nothing(self):
        path = workbook([
            ["NOBODY 2", datetime.datetime(2025, 8, 15), "Scope", 5.1, "R", 89, None],
        ])
        output = self.run_import(path, dry_run=True)
        self.assertEqual(StudioTitle.objects.count(), 0)
        self.assertEqual(Studio.objects.count(), 0)
        self.assertIn("dry run", output.lower())

    def test_unknown_studio_slug_is_an_error(self):
        path = workbook([])
        with self.assertRaises(CommandError):
            call_command("import_studio_catalog", studio="pathe", file=path)

    def test_missing_file_is_an_error(self):
        with self.assertRaises(CommandError):
            call_command(
                "import_studio_catalog", studio="universal", file="/nope.xlsx"
            )

    def test_missing_sheet_is_an_error(self):
        path = workbook([], sheet_name="something else")
        with self.assertRaises(CommandError):
            call_command(
                "import_studio_catalog", studio="universal", file=path
            )
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python manage.py test cinema.tests.test_import_studio_catalog -v 2`
Expected: FAIL — `CommandError: Unknown command: 'import_studio_catalog'`

- [ ] **Step 4: Write the command**

Create `cinema/management/commands/import_studio_catalog.py`:

```python
"""Import a studio's DCP availability list into StudioTitle.

Studios send a spreadsheet of everything they will rent us. This loads one
into the catalog behind the /sponsor/ page.

Idempotent: rows are matched on (studio, original_title, release_date), so
re-running after a studio ships an updated list adds the new titles and
refreshes the old ones without duplicating anything. `is_available` and
`hidden_reason` are deliberately NOT refreshed — a title you hid must stay
hidden across the next catalog drop.

Safe to run on prod:
    python manage.py import_studio_catalog --studio universal \\
        --file "Universal DCP List - Updated 3.4.26.xlsx"

Use --dry-run first to see the counts without writing.
"""

from pathlib import Path
from typing import Any

from cinema.models import Studio, StudioTitle
from cinema.studio_catalog import clean_cell, normalize_title, parse_runtime
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# Slug -> display name. A studio must be listed here before its list can be
# imported, so a typo in --studio fails loudly instead of silently creating
# a "Univrsal" catalog nobody can find.
KNOWN_STUDIOS = {
    "universal": "Universal Pictures",
}

DEFAULT_SHEET = "by TITLE"

# Column order in every studio list we have seen so far.
COL_TITLE = 0
COL_RELEASE = 1
COL_ASPECT = 2
COL_AUDIO = 3
COL_RATING = 4
COL_RUNTIME = 5
COL_NOTES = 6


class ParsedRow:
    """One spreadsheet row, cleaned up."""

    def __init__(self, cells: tuple) -> None:
        def cell(index: int) -> Any:
            return cells[index] if index < len(cells) else None

        raw_title = clean_cell(cell(COL_TITLE))
        self.original_title = raw_title
        self.title = normalize_title(raw_title)

        release = cell(COL_RELEASE)
        self.release_date = release.date() if hasattr(release, "date") else None

        self.aspect_ratio = clean_cell(cell(COL_ASPECT))
        self.audio = clean_cell(cell(COL_AUDIO))
        self.mpa_rating = clean_cell(cell(COL_RATING))
        self.runtime_minutes, self.runtime_raw = parse_runtime(cell(COL_RUNTIME))
        self.notes = clean_cell(cell(COL_NOTES))

    @property
    def key(self) -> tuple[str, object]:
        return (self.original_title, self.release_date)

    @property
    def filled(self) -> int:
        """How many optional fields carry a value — the variant tie-break."""
        return sum(
            1
            for value in (
                self.aspect_ratio, self.audio, self.mpa_rating,
                self.runtime_raw, self.notes,
            )
            if value
        )

    def summary(self) -> str:
        """One-line description of this variant, for `variant_note`."""
        bits = [
            self.notes,
            f"{self.runtime_minutes} min" if self.runtime_minutes else "",
            self.audio,
            self.mpa_rating,
        ]
        return ", ".join(bit for bit in bits if bit)


class Command(BaseCommand):
    help = "Import a studio's DCP availability spreadsheet into StudioTitle."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--studio", required=True,
            help=f"Studio slug. One of: {', '.join(sorted(KNOWN_STUDIOS))}",
        )
        parser.add_argument("--file", required=True, help="Path to the .xlsx file.")
        parser.add_argument(
            "--sheet", default=DEFAULT_SHEET,
            help=(
                "Worksheet to read. Universal ships 'by DATE' and 'by TITLE' "
                "with identical content, so the default is fine."
            ),
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        slug = options["studio"]
        if slug not in KNOWN_STUDIOS:
            raise CommandError(
                f"Unknown studio '{slug}'. "
                f"Known: {', '.join(sorted(KNOWN_STUDIOS))}"
            )

        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"No such file: {path}")

        rows = self._read(path, options["sheet"])
        groups = self._group(rows)

        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing written."))
            self.stdout.write(
                f"Would import {len(groups)} titles from {len(rows)} rows "
                f"({len(rows) - len(groups)} variants collapsed)."
            )
            return

        with transaction.atomic():
            studio, _ = Studio.objects.get_or_create(
                slug=slug, defaults={"name": KNOWN_STUDIOS[slug]}
            )
            created, updated, collapsed = self._write(studio, groups)

        self.stdout.write(
            self.style.SUCCESS(
                f"{studio.name}: {created} created, {updated} updated, "
                f"{collapsed} variants collapsed, {len(rows)} rows read."
            )
        )

    def _read(self, path: Path, sheet: str) -> list[ParsedRow]:
        # Imported here so the module loads even if openpyxl is missing,
        # which keeps `manage.py help` working with a clearer error.
        import openpyxl

        book = openpyxl.load_workbook(path, data_only=True, read_only=True)
        if sheet not in book.sheetnames:
            raise CommandError(
                f"No sheet named '{sheet}' in {path.name}. "
                f"Found: {', '.join(book.sheetnames)}"
            )
        worksheet = book[sheet]
        rows = []
        for cells in worksheet.iter_rows(min_row=2, values_only=True):
            if not cells or not clean_cell(cells[COL_TITLE]):
                continue
            rows.append(ParsedRow(cells))
        book.close()
        return rows

    def _group(self, rows: list[ParsedRow]) -> dict:
        """Bucket rows by natural key, preserving sheet order within a bucket."""
        groups: dict = {}
        for row in rows:
            groups.setdefault(row.key, []).append(row)
        return groups

    def _primary(self, group: list[ParsedRow]) -> ParsedRow:
        """Pick the row that best represents a group of DCP variants.

        Longest runtime wins (the roadshow cut, the reconstruction). Ties go
        to the most complete row, then to sheet order — without that last
        step the two Dracula 1931-02-13 rows, identical but for their audio,
        would import differently run to run.
        """
        best = group[0]
        for row in group[1:]:
            if (row.runtime_minutes or 0) > (best.runtime_minutes or 0):
                best = row
            elif (row.runtime_minutes or 0) == (best.runtime_minutes or 0):
                if row.filled > best.filled:
                    best = row
        return best

    def _write(self, studio: Studio, groups: dict) -> tuple[int, int, int]:
        created = updated = collapsed = 0

        for group in groups.values():
            primary = self._primary(group)
            others = [row for row in group if row is not primary]
            collapsed += len(others)

            # Skip any variant that describes the same thing as the primary.
            # Notting Hill is listed twice, identically — without this the
            # page would advertise an "also available" version that is just
            # the row itself.
            seen = {primary.summary()}
            summaries = []
            for row in others:
                summary = row.summary()
                if not summary or summary in seen:
                    continue
                seen.add(summary)
                summaries.append(summary)

            variant_note = (
                f"Also available: {'; '.join(summaries)}"[:300] if summaries else ""
            )

            _, was_created = StudioTitle.objects.update_or_create(
                studio=studio,
                original_title=primary.original_title,
                release_date=primary.release_date,
                defaults={
                    "title": primary.title,
                    "aspect_ratio": primary.aspect_ratio,
                    "audio": primary.audio,
                    "mpa_rating": primary.mpa_rating,
                    "runtime_minutes": primary.runtime_minutes,
                    "runtime_raw": primary.runtime_raw,
                    "notes": primary.notes,
                    "variant_note": variant_note,
                    # NOTE: is_available / hidden_reason are absent on purpose.
                    # A re-import must never un-hide a title.
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        return created, updated, collapsed
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python manage.py test cinema.tests.test_import_studio_catalog -v 2`
Expected: PASS (all tests)

- [ ] **Step 6: Dry-run against the real Universal list**

```bash
.venv/bin/python manage.py import_studio_catalog \
  --studio universal \
  --file "/Users/bgoding/Documents/Universal DCP List - Updated 3.4.26.xlsx" \
  --dry-run
```

Expected: `Would import 1140 titles from 1148 rows (8 variants collapsed).`
If those numbers differ, stop and investigate before importing for real —
they were verified against the spreadsheet while writing the spec.

- [ ] **Step 7: Import for real**

```bash
.venv/bin/python manage.py import_studio_catalog \
  --studio universal \
  --file "/Users/bgoding/Documents/Universal DCP List - Updated 3.4.26.xlsx"
```

Expected: `Universal Pictures: 1140 created, 0 updated, 8 variants collapsed, 1148 rows read.`

Then confirm idempotency by running the exact same command again.
Expected: `0 created, 1140 updated, ...` and still 1140 rows:

```bash
.venv/bin/python manage.py shell -c \
  "from cinema.models import StudioTitle; print(StudioTitle.objects.count())"
```
Expected: `1140`

- [ ] **Step 8: Lint and commit**

```bash
.venv/bin/python -m flake8 cinema/
git add cinema/management/ cinema/tests/test_import_studio_catalog.py requirements.txt
git commit -m "feat(cinema): import_studio_catalog command and openpyxl dependency"
```

---

### Task 4: Sponsorship tiers and the `/sponsor/` page

The pitch, the tiers, and the searchable table. The inquiry form arrives in
Task 5 — this task ends with a page a business can read and browse.

**Files:**
- Modify: `web/constants.py`
- Modify: `web/views.py`
- Modify: `web/urls.py`
- Modify: `web/sitemaps.py`
- Modify: `templates/partials/footer.html`
- Create: `web/templates/web/sponsor.html`
- Create: `static/css/SponsorPage.css`
- Modify: `frontend/styles/main.css`
- Create: `web/tests/test_sponsor.py`

**Interfaces:**
- Consumes: `StudioTitle.objects.available()` (Task 2).
- Produces:
  - `web.constants.SPONSORSHIP_TIERS: list[dict]` with keys `key`, `name`, `price`, `eyebrow`, `includes`
  - `web.constants.SPONSORSHIP_POPCORN_CAP: int`
  - `web.views.SponsorView`
  - URL name `sponsor` at `/sponsor/`

- [ ] **Step 1: Write the failing tests**

Create `web/tests/test_sponsor.py`:

```python
import datetime

from cinema.models import Studio, StudioTitle
from django.test import TestCase
from django.urls import reverse


class SponsorPageTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )
        cls.wild = StudioTitle.objects.create(
            studio=cls.studio, original_title="WILD ROBOT, THE",
            title="The Wild Robot", release_date=datetime.date(2024, 9, 27),
            mpa_rating="PG", runtime_minutes=102, aspect_ratio="Scope",
        )
        cls.jaws = StudioTitle.objects.create(
            studio=cls.studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20),
            mpa_rating="PG", runtime_minutes=124,
        )
        cls.hidden = StudioTitle.objects.create(
            studio=cls.studio, original_title="HIDDEN ONE", title="Hidden One",
            release_date=datetime.date(2020, 1, 1), is_available=False,
        )

    def test_page_returns_200_and_uses_templates(self):
        response = self.client.get(reverse("sponsor"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/sponsor.html")

    def test_no_template_comment_leaks_into_page(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertNotIn("{#", html)
        self.assertNotIn("{% comment %}", html)

    def test_lists_available_titles_only(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn("The Wild Robot", html)
        self.assertIn("Jaws", html)
        self.assertNotIn("Hidden One", html)

    def test_inactive_studio_titles_are_hidden(self):
        self.studio.is_active = False
        self.studio.save()
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertNotIn("The Wild Robot", html)

    def test_search_filters_by_title(self):
        response = self.client.get(reverse("sponsor"), {"q": "wild"})
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, ["The Wild Robot"])

    def test_search_is_case_insensitive(self):
        response = self.client.get(reverse("sponsor"), {"q": "JAWS"})
        self.assertEqual([t.title for t in response.context["titles"]], ["Jaws"])

    def test_decade_filter(self):
        response = self.client.get(reverse("sponsor"), {"decade": "1970"})
        self.assertEqual([t.title for t in response.context["titles"]], ["Jaws"])

    def test_rating_filter(self):
        response = self.client.get(reverse("sponsor"), {"rating": "PG"})
        self.assertEqual(len(response.context["titles"]), 2)

    def test_sort_by_year_descending(self):
        response = self.client.get(reverse("sponsor"), {"sort": "-year"})
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, ["The Wild Robot", "Jaws"])

    def test_unknown_sort_falls_back_to_title(self):
        # Never interpolate raw querystring into order_by.
        response = self.client.get(reverse("sponsor"), {"sort": "runtime; DROP TABLE"})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, ["Jaws", "The Wild Robot"])

    def test_pagination_is_fifty_per_page(self):
        response = self.client.get(reverse("sponsor"))
        self.assertEqual(response.context["paginator"].per_page, 50)

    def test_tiers_are_in_context_with_the_agreed_prices(self):
        tiers = self.client.get(reverse("sponsor")).context["tiers"]
        self.assertEqual([t["price"] for t in tiers], [299, 499, 799])

    def test_page_names_the_real_sponsor_example(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn("A.H. Custom Carpentry", html)
        self.assertIn("The Wild Robot", html)

    def test_full_house_tier_states_the_guest_cap_and_size(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn("first 100 guests", html)
        self.assertIn("Medium", html)

    def test_filter_choices_come_from_available_titles(self):
        context = self.client.get(reverse("sponsor")).context
        self.assertIn("PG", context["ratings"])
        self.assertIn(1970, context["decades"])
        self.assertIn(2020, context["decades"])


class SponsorSitemapTests(TestCase):
    def test_sponsor_is_in_the_sitemap(self):
        html = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("/sponsor/", html)

    def test_sponsor_is_in_the_site_navigation(self):
        # nav.html loops SITE_CONFIG["navigation"]; the trailing slash matters
        # because a bare /sponsor would 301 on every click.
        html = self.client.get("/").content.decode()
        self.assertIn('href="/sponsor/"', html)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python manage.py test web.tests.test_sponsor -v 2`
Expected: FAIL — `NoReverseMatch: Reverse for 'sponsor' not found`

- [ ] **Step 3: Add the tier constants**

Append to `web/constants.py`:

```python
# Sponsorship program. A local business underwrites a screening; the tiers
# stack, each one adding to the one before it.
#
# Pricing is derived, not guessed: Universal charges a flat $200 to book a
# library title, so tier 1 leaves $99 for staff, projection and the promotion
# we do for the sponsor. Tier 2 adds free public admission — cheap for us,
# because at ~6 admissions per showtime a free promoted screening fills a room
# that would otherwise be near-empty rather than displacing ticket sales.
# Tier 3 adds popcorn: 100 mediums retail at $625, but at a 30-50% concession
# attach rate the real cost is ~$250 of forgone sales plus ~$60 of materials.
# See docs/superpowers/specs/2026-08-23-film-sponsorships-design.md.
SPONSORSHIP_POPCORN_CAP = 100

SPONSORSHIP_TIERS = [
    {
        "key": "presenting",
        "name": "Presenting Sponsor",
        "eyebrow": "Cover the film",
        "price": 299,
        "includes": [
            "We book the title you pick",
            "Social media posts in the run-up to the show",
            "Your name on the marquee",
            "Your name on screen before the film",
        ],
    },
    {
        "key": "community",
        "name": "Community Screening",
        "eyebrow": "Cover the film and admission",
        "price": 499,
        "includes": [
            "We book the title you pick",
            "Social media posts in the run-up to the show",
            "Your name on the marquee",
            "Your name on screen before the film",
            "Admission is free for everyone who comes",
        ],
    },
    {
        "key": "full_house",
        "name": "Full House",
        "eyebrow": "Cover the film, admission and popcorn",
        "price": 799,
        "includes": [
            "We book the title you pick",
            "Social media posts in the run-up to the show",
            "Your name on the marquee",
            "Your name on screen before the film",
            "Admission is free for everyone who comes",
            "Medium buttered popcorn for the first 100 guests",
        ],
    },
]
```

- [ ] **Step 4: Add the view**

Add to `web/views.py` (import `StudioTitle` from `cinema.models`, `ListView` from
`django.views.generic`, and `SPONSORSHIP_TIERS`, `SPONSORSHIP_POPCORN_CAP` from
`web.constants`):

```python
# Whitelist of sort keys. The querystring never reaches order_by directly.
SPONSOR_SORTS = {
    "title": "title",
    "-title": "-title",
    "year": "release_date",
    "-year": "-release_date",
    "runtime": "runtime_minutes",
    "-runtime": "-runtime_minutes",
}


class SponsorView(ListView):
    """/sponsor/ — the pitch, the tiers, and what a business can pick from.

    Server-side filtering and pagination rather than a client-side table:
    1,140 rows is manageable either way, but the catalog grows with every
    studio added, and this shape survives 5,000 titles without a rewrite.
    """

    template_name = "web/sponsor.html"
    context_object_name = "titles"
    paginate_by = 50

    def get_queryset(self):
        queryset = StudioTitle.objects.available().select_related("studio")

        query = (self.request.GET.get("q") or "").strip()
        if query:
            queryset = queryset.filter(title__icontains=query)

        rating = (self.request.GET.get("rating") or "").strip()
        if rating:
            queryset = queryset.filter(mpa_rating=rating)

        decade = (self.request.GET.get("decade") or "").strip()
        if decade.isdigit():
            start = int(decade)
            queryset = queryset.filter(
                release_date__year__gte=start, release_date__year__lt=start + 10
            )

        sort = self.request.GET.get("sort") or "title"
        field = SPONSOR_SORTS.get(sort, "title")
        # pk breaks ties so pagination stays stable across pages.
        return queryset.order_by(field, "pk")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        available = StudioTitle.objects.available()

        years = available.exclude(release_date__isnull=True).values_list(
            "release_date__year", flat=True
        )
        ctx.update(
            {
                "tiers": SPONSORSHIP_TIERS,
                "popcorn_cap": SPONSORSHIP_POPCORN_CAP,
                "total_count": available.count(),
                "ratings": sorted(
                    r for r in set(
                        available.values_list("mpa_rating", flat=True)
                    ) if r
                ),
                "decades": sorted({(year // 10) * 10 for year in years}, reverse=True),
                "q": self.request.GET.get("q", ""),
                "selected_rating": self.request.GET.get("rating", ""),
                "selected_decade": self.request.GET.get("decade", ""),
                "sort": self.request.GET.get("sort", "title"),
            }
        )
        return ctx
```

- [ ] **Step 5: Wire the URL, sitemap and navigation**

`web/urls.py` — add `SponsorView` to the imports and this path beside `/rentals/`:

```python
    path("sponsor/", SponsorView.as_view(), name="sponsor"),
```

`web/sitemaps.py` — add `"sponsor"` to `StaticViewSitemap.items()`.

**Navigation, not the footer.** `templates/partials/footer.html` has no
page-link section — its "Quick Links" columns are deliberately commented out to
match the original React source, and the only link in it is the phone number.
Site navigation is data-driven from `SITE_CONFIG["navigation"]`, which
`templates/partials/nav.html` loops over. Add the entry to `web/constants.py`
after Rentals:

```python
        {"label": "Rentals", "href": "/rentals/"},
        {"label": "Sponsor", "href": "/sponsor/"},
```

The trailing slash is required — `nav.html` emits `item.href` verbatim for
paths starting with `/`, and a bare `/sponsor` would cost a 301 on every click
and every crawl. The comment already in that list says exactly this; leave it
in place.

- [ ] **Step 6: Write the template**

Create `web/templates/web/sponsor.html`. Uses Django 5.1+'s built-in
`{% querystring %}` tag, so filter and sort links preserve the other params
without a custom template tag.

```html
{% extends "base.html" %}
{% load static %}

{% block title %}Sponsor a Film | Fort Kent Cinema{% endblock %}
{% block description %}Put your business behind a movie. Local businesses sponsor screenings at Fort Kent Cinema — cover the film, the admission, even the popcorn, and we tell the whole town who made it happen.{% endblock %}
{% block og_title %}Sponsor a Film | Fort Kent Cinema{% endblock %}
{% block og_description %}Local businesses sponsor screenings at Maine's northernmost picture show. Browse what we can book and start a conversation.{% endblock %}

{% block content %}
<div class="sponsor-page">
  <div class="sponsor-container">

    <header class="sponsor-header">
      <a href="/" class="sponsor-back">&larr; Back to Home</a>
      <h1 class="sponsor-title">SPONSOR A FILM</h1>
      <p class="sponsor-subtitle">
        Put your business behind a movie — and we'll tell the whole town who made it happen.
      </p>
    </header>

    {% comment %}
      The worked example does the selling. A named local business is far more
      persuasive than "Your Business Here", and A.H. Custom Carpentry approved
      being named.
    {% endcomment %}
    <section class="sponsor-example">
      <p class="sponsor-example__eyebrow">Happening this month</p>
      <h2 class="sponsor-example__title">
        A.H. Custom Carpentry is sponsoring <em>The Wild Robot</em>
      </h2>
      <p class="sponsor-example__body">
        They're covering the cost of bringing the film to Fort Kent. In return,
        their name goes out with every post we make about the show, it's on the
        marquee on Hall Street, and it's on screen before the lights go down.
        One local business, one movie, a whole town that knows who paid for it.
      </p>
      <p class="sponsor-example__body">
        That's the whole idea. You pick a film, we book it, and the credit is
        yours.
      </p>
    </section>

    <section class="sponsor-tiers" id="tiers">
      <header class="sponsor-tiers__header">
        <h2 class="sponsor-tiers__title">What you can cover</h2>
        <p class="sponsor-tiers__note">
          Each level builds on the one before it. Prices start here and depend
          on the title — some films cost us more to book than others.
        </p>
      </header>
      <div class="sponsor-tiers__grid">
        {% for tier in tiers %}
          <article class="sponsor-tier">
            <p class="sponsor-tier__eyebrow">{{ tier.eyebrow }}</p>
            <h3 class="sponsor-tier__name">{{ tier.name }}</h3>
            <p class="sponsor-tier__price">
              <span class="sponsor-tier__from">from</span>${{ tier.price }}
            </p>
            <ul class="sponsor-tier__list">
              {% for item in tier.includes %}
                <li>{{ item }}</li>
              {% endfor %}
            </ul>
            <a href="#inquire" class="btn btn-primary sponsor-tier__cta">
              Start a conversation
            </a>
          </article>
        {% endfor %}
      </div>
    </section>

    <section class="sponsor-catalog" id="catalog">
      <header class="sponsor-catalog__header">
        <h2 class="sponsor-catalog__title">What we can book</h2>
        <p class="sponsor-catalog__note">
          {{ total_count }} titles available from Universal right now. More
          studios coming. Don't see what you want? Ask anyway — we'll find out.
        </p>
      </header>

      <form class="sponsor-filters" method="get" action="{% url 'sponsor' %}">
        <label class="sponsor-filters__field">
          <span class="sponsor-filters__label">Search titles</span>
          <input type="search" name="q" value="{{ q }}" placeholder="Jurassic Park" />
        </label>

        <label class="sponsor-filters__field">
          <span class="sponsor-filters__label">Rating</span>
          <select name="rating">
            <option value="">Any</option>
            {% for rating in ratings %}
              <option value="{{ rating }}" {% if rating == selected_rating %}selected{% endif %}>{{ rating }}</option>
            {% endfor %}
          </select>
        </label>

        <label class="sponsor-filters__field">
          <span class="sponsor-filters__label">Decade</span>
          <select name="decade">
            <option value="">Any</option>
            {% for decade in decades %}
              <option value="{{ decade }}" {% if decade|stringformat:"s" == selected_decade %}selected{% endif %}>{{ decade }}s</option>
            {% endfor %}
          </select>
        </label>

        <input type="hidden" name="sort" value="{{ sort }}" />
        <button type="submit" class="btn btn-primary">Search</button>
        <a href="{% url 'sponsor' %}" class="sponsor-filters__reset">Clear</a>
      </form>

      {% if titles %}
        <div class="sponsor-table__scroll">
          <table class="sponsor-table">
            <thead>
              <tr>
                <th><a href="{% querystring sort='title' page=None %}">Title</a></th>
                <th><a href="{% querystring sort='-year' page=None %}">Year</a></th>
                <th>Rating</th>
                <th><a href="{% querystring sort='runtime' page=None %}">Runtime</a></th>
                <th>Format</th>
              </tr>
            </thead>
            <tbody>
              {% for title in titles %}
                <tr>
                  <td class="sponsor-table__title">
                    {{ title.title }}
                    {% if title.variant_note %}
                      <span class="sponsor-table__variant">{{ title.variant_note }}</span>
                    {% endif %}
                  </td>
                  <td>{{ title.release_year|default_if_none:"—" }}</td>
                  <td>{{ title.mpa_rating|default:"—" }}</td>
                  <td>{{ title.runtime_raw|default:title.runtime_minutes|default:"—" }}</td>
                  <td class="sponsor-table__format">{{ title.format_summary|default:"—" }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>

        {% if page_obj.has_other_pages %}
          <nav class="sponsor-pagination">
            {% if page_obj.has_previous %}
              <a href="{% querystring page=page_obj.previous_page_number %}">&larr; Previous</a>
            {% endif %}
            <span class="sponsor-pagination__status">
              Page {{ page_obj.number }} of {{ paginator.num_pages }}
            </span>
            {% if page_obj.has_next %}
              <a href="{% querystring page=page_obj.next_page_number %}">Next &rarr;</a>
            {% endif %}
          </nav>
        {% endif %}
      {% else %}
        <p class="sponsor-catalog__empty">
          Nothing matched that. <a href="{% url 'sponsor' %}">Clear the filters</a>
          and try again.
        </p>
      {% endif %}
    </section>

    {% comment %} The inquiry form is added in Task 5. {% endcomment %}
    <section class="sponsor-inquire" id="inquire">
      <h2 class="sponsor-inquire__title">Interested?</h2>
      <p class="sponsor-inquire__body">
        Call us at {{ site_config.cinema.phone }} and we'll talk it through.
      </p>
    </section>

  </div>
</div>
{% endblock %}
```

Check the exact key for the phone number in `web/constants.py` (`SITE_CONFIG`
has `"phone": "(207) 231-5287"` under a contact-ish key) and match the path the
other templates use — grep for `phone` in `web/templates/` and copy that.

- [ ] **Step 7: Add the stylesheet and register it**

Create `static/css/SponsorPage.css`. The site is Art Deco — champagne gold on
charcoal, Poiret One display / Playfair Display headings / Cormorant Garamond
body — all via the custom properties in `static/css/variables.css`. Never
hard-code a colour or a font.

```css
/* Sponsor page — the pitch, the tiers, and the bookable catalog.
 * Structure mirrors PrivateRentalsPage.css: full-height gradient, centred
 * 1200px container, section rhythm on --spacing-2xl.
 */

.sponsor-page {
  min-height: 100vh;
  padding: var(--spacing-lg);
  padding-top: calc(80px + var(--spacing-xl));
  background: linear-gradient(
    180deg,
    var(--color-bg-charcoal) 0%,
    var(--color-bg-dark) 100%
  );
}

.sponsor-container {
  max-width: 1200px;
  margin: 0 auto;
}

/* Header */
.sponsor-header {
  text-align: center;
  margin-bottom: var(--spacing-2xl);
}

.sponsor-back {
  display: inline-block;
  font-family: var(--font-display);
  font-size: 0.9rem;
  letter-spacing: 2px;
  color: var(--color-gold);
  text-decoration: none;
  margin-bottom: var(--spacing-md);
  transition: all var(--transition-base);
}

.sponsor-back:hover {
  color: var(--color-gold-warm);
  text-shadow: 0 0 10px var(--color-gold-glow);
}

.sponsor-title {
  font-family: var(--font-display);
  font-size: 3rem;
  letter-spacing: 6px;
  color: var(--color-gold);
  text-shadow: 0 0 30px var(--color-gold-glow);
  margin-bottom: var(--spacing-sm);
}

.sponsor-subtitle {
  font-family: var(--font-heading);
  font-size: 1.25rem;
  color: var(--color-cream-muted);
  font-style: italic;
}

/* Worked example — the part that actually sells */
.sponsor-example {
  background: var(--color-bg-card);
  border: 1px solid var(--color-brass);
  border-radius: 4px;
  padding: var(--spacing-xl);
  margin-bottom: var(--spacing-2xl);
}

.sponsor-example__eyebrow {
  font-family: var(--font-display);
  font-size: 0.8rem;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--color-brass-light);
  margin-bottom: var(--spacing-xs);
}

.sponsor-example__title {
  font-family: var(--font-heading);
  font-size: 1.75rem;
  color: var(--color-gold);
  margin-bottom: var(--spacing-md);
}

.sponsor-example__body {
  font-family: var(--font-body);
  font-size: 1.1rem;
  line-height: 1.7;
  color: var(--color-cream);
  margin-bottom: var(--spacing-sm);
}

/* Tiers */
.sponsor-tiers {
  margin-bottom: var(--spacing-2xl);
}

.sponsor-tiers__header {
  text-align: center;
  margin-bottom: var(--spacing-lg);
}

.sponsor-tiers__title {
  font-family: var(--font-display);
  font-size: 2rem;
  letter-spacing: 4px;
  color: var(--color-gold);
  text-shadow: 0 0 15px var(--color-gold-glow);
  margin-bottom: var(--spacing-sm);
}

.sponsor-tiers__note {
  font-family: var(--font-body);
  font-size: 0.95rem;
  color: var(--color-cream-muted);
  font-style: italic;
}

.sponsor-tiers__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: var(--spacing-lg);
}

.sponsor-tier {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-card);
  border: 1px solid var(--color-brass);
  border-radius: 4px;
  padding: var(--spacing-lg);
}

.sponsor-tier__eyebrow {
  font-family: var(--font-display);
  font-size: 0.75rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--color-brass-light);
}

.sponsor-tier__name {
  font-family: var(--font-heading);
  font-size: 1.4rem;
  color: var(--color-cream);
  margin: var(--spacing-xs) 0 var(--spacing-sm);
}

.sponsor-tier__price {
  font-family: var(--font-display);
  font-size: 2.5rem;
  color: var(--color-gold);
  text-shadow: 0 0 20px var(--color-gold-glow);
  margin-bottom: var(--spacing-md);
}

.sponsor-tier__from {
  font-size: 0.9rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--color-cream-muted);
  margin-right: var(--spacing-xs);
}

.sponsor-tier__list {
  font-family: var(--font-body);
  font-size: 1rem;
  line-height: 1.7;
  color: var(--color-cream);
  list-style: none;
  padding: 0;
  margin: 0 0 var(--spacing-lg);
  flex: 1;
}

.sponsor-tier__list li {
  padding-left: 1.25rem;
  position: relative;
}

.sponsor-tier__list li::before {
  content: '◆';
  position: absolute;
  left: 0;
  color: var(--color-brass-light);
  font-size: 0.7rem;
  top: 0.4em;
}

.sponsor-tier__cta {
  align-self: flex-start;
}

/* Catalog */
.sponsor-catalog {
  margin-bottom: var(--spacing-2xl);
}

.sponsor-catalog__header {
  text-align: center;
  margin-bottom: var(--spacing-lg);
}

.sponsor-catalog__title {
  font-family: var(--font-display);
  font-size: 2rem;
  letter-spacing: 4px;
  color: var(--color-gold);
  text-shadow: 0 0 15px var(--color-gold-glow);
  margin-bottom: var(--spacing-sm);
}

.sponsor-catalog__note,
.sponsor-catalog__empty {
  font-family: var(--font-body);
  font-size: 0.95rem;
  color: var(--color-cream-muted);
}

.sponsor-catalog__empty {
  text-align: center;
  padding: var(--spacing-xl) 0;
}

/* Filters */
.sponsor-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--color-bg-card);
  border: 1px solid var(--color-brass);
  border-radius: 4px;
}

.sponsor-filters__field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.sponsor-filters__label {
  font-family: var(--font-display);
  font-size: 0.75rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--color-cream-muted);
}

.sponsor-filters input,
.sponsor-filters select {
  font-family: var(--font-body);
  font-size: 1rem;
  padding: 0.5rem 0.75rem;
  background: var(--color-bg-dark);
  border: 1px solid var(--color-brass);
  border-radius: 3px;
  color: var(--color-cream);
  min-width: 10rem;
}

.sponsor-filters input:focus,
.sponsor-filters select:focus {
  outline: 2px solid var(--color-gold);
  outline-offset: 1px;
}

.sponsor-filters__reset {
  font-family: var(--font-body);
  color: var(--color-cream-muted);
  text-decoration: underline;
}

/* Table — must scroll inside itself; the page never scrolls sideways. */
.sponsor-table__scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border: 1px solid var(--color-brass);
  border-radius: 4px;
}

.sponsor-table {
  width: 100%;
  min-width: 44rem;
  border-collapse: collapse;
  font-family: var(--font-body);
  font-size: 1rem;
  color: var(--color-cream);
}

.sponsor-table th,
.sponsor-table td {
  text-align: left;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--color-burgundy);
  vertical-align: top;
}

.sponsor-table thead th {
  font-family: var(--font-display);
  font-size: 0.8rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--color-brass-light);
  background: var(--color-bg-charcoal-dark);
  position: sticky;
  top: 0;
}

.sponsor-table thead th a {
  color: inherit;
  text-decoration: none;
}

.sponsor-table thead th a:hover {
  color: var(--color-gold);
}

.sponsor-table tbody tr:hover {
  background: var(--color-bg-card);
}

.sponsor-table__title {
  font-weight: 600;
}

.sponsor-table__variant,
.sponsor-table__format {
  display: block;
  font-size: 0.85rem;
  color: var(--color-cream-muted);
}

/* Pagination */
.sponsor-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  margin-top: var(--spacing-lg);
  font-family: var(--font-body);
}

.sponsor-pagination a {
  color: var(--color-gold);
  text-decoration: none;
}

.sponsor-pagination a:hover {
  text-shadow: 0 0 10px var(--color-gold-glow);
}

.sponsor-pagination__status {
  color: var(--color-cream-muted);
  font-size: 0.9rem;
}

/* Inquiry */
.sponsor-inquire {
  background: var(--color-bg-card);
  border: 1px solid var(--color-brass);
  border-radius: 4px;
  padding: var(--spacing-xl);
}

.sponsor-inquire__title {
  font-family: var(--font-display);
  font-size: 2rem;
  letter-spacing: 4px;
  color: var(--color-gold);
  margin-bottom: var(--spacing-sm);
}

.sponsor-inquire__body {
  font-family: var(--font-body);
  font-size: 1.05rem;
  color: var(--color-cream);
  margin-bottom: var(--spacing-lg);
}

@media (max-width: 640px) {
  .sponsor-title {
    font-size: 2rem;
    letter-spacing: 3px;
  }

  .sponsor-filters__field,
  .sponsor-filters input,
  .sponsor-filters select {
    width: 100%;
  }
}
```

Confirm the spacing and transition tokens used above exist in
`static/css/variables.css` (`--spacing-xs/sm/md/lg/xl/2xl`,
`--transition-base`). If any name differs, use the real one — do not add new
custom properties.

Register it in `frontend/styles/main.css` in the **pages** group (section 5),
after `PrivateRentalsPage.css`:

```css
@import '../../static/css/SponsorPage.css';
```

- [ ] **Step 8: Build the CSS bundle**

```bash
cd frontend && npm run build && cd ..
```
Expected: writes `static/css/bundle.css` (and `static/js/effects.js`)

- [ ] **Step 9: Run the tests to verify they pass**

Run: `.venv/bin/python manage.py test web.tests.test_sponsor -v 2`
Expected: PASS (all tests)

- [ ] **Step 10: Run the full web suite**

Run: `.venv/bin/python manage.py test web -v 1`
Expected: PASS — `web/tests/test_crawl_and_schema.py` and
`web/tests/test_sitemap.py` both walk the site, so a broken URL or template
shows up here.

- [ ] **Step 11: Lint and commit**

```bash
.venv/bin/python -m flake8 web/
git add web/ static/css/SponsorPage.css frontend/styles/main.css templates/partials/footer.html static/css/bundle.css
git commit -m "feat(web): /sponsor/ page with tiers and searchable catalog"
```

---

### Task 5: `SponsorshipInquiry` model and the inquiry form

**Files:**
- Create: `cinema/models/sponsorship_inquiry.py`
- Modify: `cinema/models/__init__.py`
- Modify: `cinema/admin.py`
- Create: `web/forms.py`
- Modify: `web/views.py`
- Modify: `web/urls.py`
- Modify: `web/templates/web/sponsor.html`
- Create: `web/tests/test_sponsor_inquiry.py`
- Create: migration via `makemigrations`

**Interfaces:**
- Consumes: `StudioTitle` (Task 2), `SPONSORSHIP_TIERS` (Task 4).
- Produces:
  - `cinema.models.SponsorshipInquiry`, `cinema.models.InquiryStatus`
  - `web.forms.SponsorshipInquiryForm`
  - URL name `sponsor_inquire` at `/sponsor/inquire`

- [ ] **Step 1: Write the failing tests**

Create `web/tests/test_sponsor_inquiry.py`:

```python
import datetime

from cinema.models import InquiryStatus, SponsorshipInquiry, Studio, StudioTitle
from django.test import TestCase
from django.urls import reverse


class SponsorInquiryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        studio = Studio.objects.create(name="Universal Pictures", slug="universal")
        cls.title = StudioTitle.objects.create(
            studio=studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20),
        )

    def payload(self, **overrides) -> dict:
        data = {
            "business_name": "A.H. Custom Carpentry",
            "contact_name": "Alex Harper",
            "email": "alex@example.com",
            "phone": "(207) 555-0100",
            "tier": "presenting",
            "studio_title": self.title.pk,
            "message": "We'd like the end of the month.",
            "website": "",
        }
        data.update(overrides)
        return data

    def test_valid_post_creates_an_inquiry(self):
        response = self.client.post(reverse("sponsor_inquire"), self.payload())
        # Post/Redirect/Get: a refresh must not resubmit the form.
        self.assertEqual(response.status_code, 302)
        self.assertIn("sent=1", response["Location"])

        inquiry = SponsorshipInquiry.objects.get()
        self.assertEqual(inquiry.business_name, "A.H. Custom Carpentry")
        self.assertEqual(inquiry.email, "alex@example.com")
        self.assertEqual(inquiry.tier, "presenting")
        self.assertEqual(inquiry.studio_title, self.title)
        self.assertEqual(inquiry.status, InquiryStatus.NEW)

    def test_success_message_is_shown_after_the_redirect(self):
        html = self.client.get(
            reverse("sponsor"), {"sent": "1"}
        ).content.decode()
        self.assertIn("Thanks", html)

    def test_error_response_is_a_full_page_not_a_fragment(self):
        # There is no htmx on public pages, so a failed POST must re-render
        # the whole page — nav, styles and all — rather than a bare partial.
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(email="nope")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/sponsor.html")

    def test_error_response_still_lists_the_catalog(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(email="nope")
        )
        self.assertContains(response, "Jaws")

    def test_title_is_optional(self):
        self.client.post(reverse("sponsor_inquire"), self.payload(studio_title=""))
        self.assertIsNone(SponsorshipInquiry.objects.get().studio_title)

    def test_tier_is_optional(self):
        self.client.post(reverse("sponsor_inquire"), self.payload(tier=""))
        self.assertEqual(SponsorshipInquiry.objects.get().tier, "")

    def test_missing_business_name_is_rejected(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(business_name="")
        )
        self.assertEqual(SponsorshipInquiry.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_invalid_email_is_rejected(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(email="not-an-email")
        )
        self.assertEqual(SponsorshipInquiry.objects.count(), 0)
        self.assertContains(response, "valid email")

    def test_submitted_values_survive_a_validation_error(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(email="nope")
        )
        self.assertContains(response, "A.H. Custom Carpentry")

    def test_honeypot_silently_succeeds_without_creating_a_row(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(website="http://spam.example")
        )
        # Indistinguishable from success, so a bot learns nothing.
        self.assertEqual(response.status_code, 302)
        self.assertIn("sent=1", response["Location"])
        self.assertEqual(SponsorshipInquiry.objects.count(), 0)

    def test_client_ip_is_recorded(self):
        self.client.post(
            reverse("sponsor_inquire"), self.payload(), REMOTE_ADDR="203.0.113.9"
        )
        self.assertEqual(SponsorshipInquiry.objects.get().ip, "203.0.113.9")

    def test_get_redirects_to_the_page(self):
        response = self.client.get(reverse("sponsor_inquire"))
        self.assertRedirects(response, reverse("sponsor"))


class SponsorFormRenderTests(TestCase):
    def test_form_is_on_the_sponsor_page(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn('name="business_name"', html)
        self.assertIn('name="email"', html)
        self.assertIn('id="inquire"', html)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python manage.py test web.tests.test_sponsor_inquiry -v 2`
Expected: FAIL — `ImportError: cannot import name 'SponsorshipInquiry'`

- [ ] **Step 3: Write the model**

Create `cinema/models/sponsorship_inquiry.py`:

```python
from django.db import models


class InquiryStatus(models.TextChoices):
    NEW = "NEW", "New"
    CONTACTED = "CONTACTED", "Contacted"
    WON = "WON", "Won"
    LOST = "LOST", "Lost"


class SponsorshipInquiry(models.Model):
    """A business asking about sponsoring a screening.

    Nothing in this project sends mail, so this row IS the notification: the
    dashboard lists it and the smart-alert strip counts the NEW ones. A lead
    that sits unseen is a lost sponsor, which is why it is surfaced twice.
    """

    business_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    message = models.TextField(blank=True)

    # Both optional: a business may want to sponsor *something* without
    # having picked a film or a level yet.
    studio_title = models.ForeignKey(
        "cinema.StudioTitle",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inquiries",
    )
    tier = models.CharField(max_length=32, blank=True)

    status = models.CharField(
        max_length=20, choices=InquiryStatus.choices, default=InquiryStatus.NEW
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Sponsorship inquiries"

    def __str__(self) -> str:
        return f"{self.business_name} ({self.get_status_display()})"
```

Add to `cinema/models/__init__.py`:

```python
from .sponsorship_inquiry import InquiryStatus, SponsorshipInquiry
```

and add `"InquiryStatus"`, `"SponsorshipInquiry"` to `__all__`.

- [ ] **Step 4: Register in the admin**

Append to `cinema/admin.py` (and add the names to the `from .models import` line):

```python
@admin.register(SponsorshipInquiry)
class SponsorshipInquiryAdmin(admin.ModelAdmin):
    list_display = (
        "business_name", "contact_name", "email", "tier", "status", "created_at",
    )
    list_filter = ("status", "tier")
    search_fields = ("business_name", "contact_name", "email")
    readonly_fields = ("created_at", "ip")
```

- [ ] **Step 5: Write the form**

Create `web/forms.py`:

```python
from cinema.models import SponsorshipInquiry, StudioTitle
from django import forms

from .constants import SPONSORSHIP_TIERS


class SponsorshipInquiryForm(forms.ModelForm):
    # Honeypot. A real person leaves this empty; bots fill every field they
    # find. Same trick as the vote page's email capture.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = SponsorshipInquiry
        fields = [
            "business_name", "contact_name", "email", "phone",
            "tier", "studio_title", "message",
        ]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "business_name": "Business or organization",
            "contact_name": "Your name",
        }
        # `tier` and `studio_title` are rebuilt in __init__ below, so their
        # labels are set there rather than here — setting them twice would
        # invite the two copies to drift apart.

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["tier"] = forms.ChoiceField(
            required=False,
            label="What you'd like to cover (optional)",
            choices=[("", "Not sure yet")]
            + [
                (t["key"], f"{t['name']} — from ${t['price']}")
                for t in SPONSORSHIP_TIERS
            ],
        )
        self.fields["studio_title"] = forms.ModelChoiceField(
            required=False,
            label="Film you have in mind (optional)",
            queryset=StudioTitle.objects.available(),
            empty_label="Not sure yet",
        )
        self.fields["phone"].required = False
        self.fields["message"].required = False

    @property
    def is_bot(self) -> bool:
        return bool(self.data.get("website"))
```

- [ ] **Step 6: Add the view and URL**

Add to `web/views.py` (import `SponsorshipInquiryForm` from `web.forms`,
`View` from `django.views`, `redirect`/`render` from `django.shortcuts`):

```python
def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class SponsorInquiryView(SponsorView):
    """POST /sponsor/inquire.

    Saves the lead and says thank you. It does not email anyone, because
    nothing in this project can send mail — the dashboard list and the
    smart-alert count are the delivery mechanism.

    Subclasses SponsorView so a validation error can re-render the whole
    page with the bound form. The vote page gets away with returning a bare
    partial because it is driven by htmx; there is no htmx on this page, so
    a fragment would arrive as an unstyled document with no navigation.

    Success redirects rather than rendering, so a refresh cannot resubmit.
    """

    def get(self, request, *args, **kwargs):
        return redirect("sponsor")

    def post(self, request, *args, **kwargs):
        form = SponsorshipInquiryForm(request.POST)
        sent_url = f"{reverse('sponsor')}?sent=1#inquire"

        if form.is_bot:
            # Indistinguishable from success, so a bot learns nothing.
            return redirect(sent_url)

        if form.is_valid():
            inquiry = form.save(commit=False)
            inquiry.ip = _client_ip(request)
            inquiry.save()
            return redirect(sent_url)

        # ListView needs object_list populated before get_context_data.
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))
```

Add `reverse` to the imports (`from django.urls import reverse`).

`web/urls.py` — add the import and this path **before** nothing in particular;
`/sponsor/inquire` cannot collide with `/sponsor/`:

```python
    path("sponsor/inquire", SponsorInquiryView.as_view(), name="sponsor_inquire"),
```

- [ ] **Step 7: Add the form partial and include it**

Create `templates/partials/sponsor_inquiry_form.html`:

```html
{% if sent %}
  <div class="sponsor-inquire__sent">
    <h3>Thanks — we've got it.</h3>
    <p>
      We'll be in touch within a couple of days to talk through dates and
      which film makes sense. If it's urgent, call {{ site_config.cinema.phone }}.
    </p>
  </div>
{% else %}
  <form class="sponsor-inquire__form" method="post" action="{% url 'sponsor_inquire' %}">
    {% csrf_token %}
    {% if form.errors %}
      <p class="sponsor-inquire__error">
        Something's missing below — have a look and try again.
      </p>
    {% endif %}
    {{ form.website }}
    {% for field in form.visible_fields %}
      <label class="sponsor-inquire__field">
        <span class="sponsor-inquire__label">{{ field.label }}</span>
        {{ field }}
        {% if field.errors %}
          <span class="sponsor-inquire__field-error">{{ field.errors|join:" " }}</span>
        {% endif %}
      </label>
    {% endfor %}
    <button type="submit" class="btn btn-primary">Send it over</button>
  </form>
{% endif %}
```

In `web/templates/web/sponsor.html`, replace the placeholder
`sponsor-inquire` section from Task 4 with:

```html
    <section class="sponsor-inquire" id="inquire">
      <h2 class="sponsor-inquire__title">Interested?</h2>
      <p class="sponsor-inquire__body">
        Tell us a bit about your business and we'll take it from there. Nothing
        is committed by sending this — it just starts the conversation.
      </p>
      {% include "partials/sponsor_inquiry_form.html" %}
    </section>
```

In `SponsorView.get_context_data`, add these two keys to the `ctx.update({...})`
call from Task 4:

```python
                # A bound form arrives via kwargs when SponsorInquiryView
                # re-renders after a validation error; otherwise start empty.
                "form": kwargs.get("form") or SponsorshipInquiryForm(),
                "sent": self.request.GET.get("sent") == "1",
```

`ListView.get_context_data` already forwards `**kwargs` into the context, so
passing `form=form` from `render_to_response` is all that is needed to reach
this. Import `SponsorshipInquiryForm` in `web/views.py`.

- [ ] **Step 8: Make the migration**

```bash
.venv/bin/python manage.py makemigrations cinema
```

- [ ] **Step 9: Add the form styles**

Append to `static/css/SponsorPage.css`:

```css
/* Inquiry form */
.sponsor-inquire__form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: var(--spacing-md);
  align-items: start;
}

.sponsor-inquire__field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.sponsor-inquire__label {
  font-family: var(--font-display);
  font-size: 0.75rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--color-cream-muted);
}

.sponsor-inquire__form input,
.sponsor-inquire__form select,
.sponsor-inquire__form textarea {
  font-family: var(--font-body);
  font-size: 1rem;
  padding: 0.6rem 0.75rem;
  background: var(--color-bg-dark);
  border: 1px solid var(--color-brass);
  border-radius: 3px;
  color: var(--color-cream);
  width: 100%;
}

.sponsor-inquire__form input:focus,
.sponsor-inquire__form select:focus,
.sponsor-inquire__form textarea:focus {
  outline: 2px solid var(--color-gold);
  outline-offset: 1px;
}

.sponsor-inquire__form textarea {
  resize: vertical;
}

/* The message field and the submit button span the whole grid. */
.sponsor-inquire__form label:has(textarea),
.sponsor-inquire__form button {
  grid-column: 1 / -1;
}

.sponsor-inquire__form button {
  justify-self: start;
}

.sponsor-inquire__error,
.sponsor-inquire__field-error {
  font-family: var(--font-body);
  color: var(--neon-gold-inner);
  font-size: 0.9rem;
}

.sponsor-inquire__error {
  grid-column: 1 / -1;
  padding: var(--spacing-sm);
  border-left: 3px solid var(--color-gold);
  background: var(--color-bg-dark);
}

.sponsor-inquire__sent h3 {
  font-family: var(--font-heading);
  font-size: 1.5rem;
  color: var(--color-gold);
  margin-bottom: var(--spacing-sm);
}

.sponsor-inquire__sent p {
  font-family: var(--font-body);
  font-size: 1.05rem;
  color: var(--color-cream);
}
```

Then rebuild:

```bash
cd frontend && npm run build && cd ..
```

- [ ] **Step 10: Run the tests to verify they pass**

```bash
.venv/bin/python manage.py test web.tests.test_sponsor_inquiry web.tests.test_sponsor -v 2
```
Expected: PASS (all tests)

- [ ] **Step 11: Lint and commit**

```bash
.venv/bin/python -m flake8 web/ cinema/
git add cinema/ web/ templates/partials/sponsor_inquiry_form.html static/css/ frontend/styles/main.css
git commit -m "feat: sponsorship inquiry form"
```

---

### Task 6: Dashboard inquiry list and smart alert

**Files:**
- Create: `dashboard/inquiry_views.py`
- Create: `dashboard/templates/dashboard/inquiries.html`
- Modify: `dashboard/urls.py`
- Modify: `dashboard/templates/dashboard/_sidebar.html`
- Modify: `dashboard/smart_alerts.py`
- Modify: `dashboard/views.py`
- Create: `dashboard/tests/test_inquiries.py`
- Modify: `dashboard/tests/test_smart_alerts.py`

**Interfaces:**
- Consumes: `SponsorshipInquiry`, `InquiryStatus` (Task 5); `StaffRequiredMixin` (`dashboard/mixins.py`).
- Produces:
  - URL names `dashboard:inquiries`, `dashboard:inquiry_status`
  - `build_smart_alerts(engagements, tomorrow_showtimes_count, today, new_inquiries=0)`

- [ ] **Step 1: Write the failing tests**

Create `dashboard/tests/test_inquiries.py`:

```python
from cinema.models import InquiryStatus, SponsorshipInquiry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class InquiryListTests(TestCase):
    def setUp(self) -> None:
        self.staff = get_user_model().objects.create_user(
            username="staff", password="pw", is_staff=True
        )
        self.inquiry = SponsorshipInquiry.objects.create(
            business_name="A.H. Custom Carpentry",
            contact_name="Alex Harper",
            email="alex@example.com",
        )

    def test_requires_staff(self):
        response = self.client.get(reverse("dashboard:inquiries"))
        self.assertNotEqual(response.status_code, 200)

    def test_lists_inquiries(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:inquiries"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A.H. Custom Carpentry")

    def test_new_count_in_context(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:inquiries"))
        self.assertEqual(response.context["new_count"], 1)

    def test_filter_by_status(self):
        SponsorshipInquiry.objects.create(
            business_name="Won Co", contact_name="B", email="b@example.com",
            status=InquiryStatus.WON,
        )
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:inquiries"), {"status": "WON"})
        self.assertContains(response, "Won Co")
        self.assertNotContains(response, "A.H. Custom Carpentry")

    def test_status_can_be_changed(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("dashboard:inquiry_status", args=[self.inquiry.pk]),
            {"status": "CONTACTED"},
        )
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.CONTACTED)

    def test_invalid_status_is_ignored(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("dashboard:inquiry_status", args=[self.inquiry.pk]),
            {"status": "BOGUS"},
        )
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.NEW)
```

Append to `dashboard/tests/test_smart_alerts.py`:

```python
class InquiryAlertTests(TestCase):
    def setUp(self) -> None:
        self.today = datetime.date(2026, 7, 10)

    def test_no_alert_when_there_are_no_new_inquiries(self):
        ids = [
            a["id"]
            for a in build_smart_alerts([], 1, self.today, new_inquiries=0)
        ]
        self.assertNotIn("new-sponsorship-inquiries", ids)

    def test_alert_is_singular_for_one(self):
        alerts = build_smart_alerts([], 1, self.today, new_inquiries=1)
        message = next(
            a["message"] for a in alerts if a["id"] == "new-sponsorship-inquiries"
        )
        self.assertEqual(message, "You have 1 new sponsorship inquiry")

    def test_alert_is_plural_for_many(self):
        alerts = build_smart_alerts([], 1, self.today, new_inquiries=3)
        message = next(
            a["message"] for a in alerts if a["id"] == "new-sponsorship-inquiries"
        )
        self.assertEqual(message, "You have 3 new sponsorship inquiries")

    def test_existing_callers_without_the_argument_still_work(self):
        # The new parameter has a default, so every existing call site and the
        # pre-existing tests above keep working unchanged.
        self.assertEqual(build_smart_alerts([], 1, self.today), [])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python manage.py test dashboard.tests.test_inquiries dashboard.tests.test_smart_alerts -v 2
```
Expected: FAIL — `NoReverseMatch: 'inquiries' is not a valid view function or pattern name`

- [ ] **Step 3: Extend `build_smart_alerts`**

In `dashboard/smart_alerts.py`, change the signature and append the alert
before `return alerts`:

```python
def build_smart_alerts(engagements, tomorrow_showtimes_count: int,
                       today: datetime.date,
                       new_inquiries: int = 0) -> list[dict]:
```

```python
    if new_inquiries > 0:
        unit = "inquiry" if new_inquiries == 1 else "inquiries"
        alerts.append({
            "id": "new-sponsorship-inquiries", "type": "info",
            "message": f"You have {new_inquiries} new sponsorship {unit}",
        })
```

- [ ] **Step 4: Feed the count from the dashboard home**

In `dashboard/views.py`, import the model and pass the count:

```python
from cinema.models import InquiryStatus, SponsorshipInquiry
```

```python
            "alerts": build_smart_alerts(
                engagements,
                tomorrow_count,
                today,
                new_inquiries=SponsorshipInquiry.objects.filter(
                    status=InquiryStatus.NEW
                ).count(),
            ),
```

- [ ] **Step 5: Write the views**

Create `dashboard/inquiry_views.py`:

```python
"""Staff surface for sponsorship inquiries.

Nothing here sends mail either — see subscriber_views. This list plus the
NEW count on the dashboard home is how a lead reaches a human.
"""

from cinema.models import InquiryStatus, SponsorshipInquiry
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .mixins import StaffRequiredMixin


class InquiryListView(StaffRequiredMixin, View):
    def get(self, request):
        inquiries = SponsorshipInquiry.objects.select_related("studio_title")

        status = (request.GET.get("status") or "").strip()
        if status in InquiryStatus.values:
            inquiries = inquiries.filter(status=status)

        return render(
            request,
            "dashboard/inquiries.html",
            {
                "inquiries": inquiries,
                "new_count": SponsorshipInquiry.objects.filter(
                    status=InquiryStatus.NEW
                ).count(),
                "statuses": InquiryStatus.choices,
                "selected_status": status,
            },
        )


class InquiryStatusView(StaffRequiredMixin, View):
    def post(self, request, pk: int):
        inquiry = get_object_or_404(SponsorshipInquiry, pk=pk)
        status = (request.POST.get("status") or "").strip()
        if status in InquiryStatus.values:
            inquiry.status = status
            inquiry.save(update_fields=["status"])
        return redirect("dashboard:inquiries")
```

- [ ] **Step 6: Write the template**

Create `dashboard/templates/dashboard/inquiries.html`, following
`dashboard/templates/dashboard/subscribers.html` exactly for structure and
reusing `dashboard/css/polls.css`:

```html
{% extends "dashboard/base_dashboard.html" %}
{% load static %}
{% block title %}Sponsorship Inquiries · LeprinceOS{% endblock %}
{% block head_extra %}<link rel="stylesheet" href="{% static 'dashboard/css/polls.css' %}" />{% endblock %}
{% block content %}
<div class="page">
  <div class="header">
    <div>
      <h1 class="title">Sponsorship Inquiries</h1>
      <p class="subtitle">
        {{ new_count }} new inquir{{ new_count|pluralize:"y,ies" }} waiting.
      </p>
    </div>
  </div>

  <form method="get" class="filters">
    <select name="status" onchange="this.form.submit()">
      <option value="">All statuses</option>
      {% for value, label in statuses %}
        <option value="{{ value }}" {% if value == selected_status %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
  </form>

  {% if inquiries %}
    <table class="table">
      <thead>
        <tr>
          <th>Business</th><th>Contact</th><th>Film</th>
          <th>Tier</th><th>Received</th><th>Status</th>
        </tr>
      </thead>
      <tbody>
        {% for inquiry in inquiries %}
          <tr>
            <td>{{ inquiry.business_name }}</td>
            <td>
              {{ inquiry.contact_name }}<br />
              <a href="mailto:{{ inquiry.email }}">{{ inquiry.email }}</a>
              {% if inquiry.phone %}<br />{{ inquiry.phone }}{% endif %}
            </td>
            <td>{{ inquiry.studio_title.title|default:"—" }}</td>
            <td>{{ inquiry.get_tier_display|default:inquiry.tier|default:"—" }}</td>
            <td>{{ inquiry.created_at|date:"M j, Y" }}</td>
            <td>
              <form method="post" action="{% url 'dashboard:inquiry_status' inquiry.pk %}">
                {% csrf_token %}
                <select name="status" onchange="this.form.submit()">
                  {% for value, label in statuses %}
                    <option value="{{ value }}" {% if value == inquiry.status %}selected{% endif %}>{{ label }}</option>
                  {% endfor %}
                </select>
              </form>
            </td>
          </tr>
          {% if inquiry.message %}
            <tr><td colspan="6" class="muted">{{ inquiry.message }}</td></tr>
          {% endif %}
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <div class="empty">
      <h2>No Inquiries Yet</h2>
      <p>They'll show up here when a business fills in the form on /sponsor/.</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

`get_tier_display` only exists if `tier` has `choices` on the model; it does
not, so the `|default:inquiry.tier` fallback above is what actually renders.
Leave both — the fallback is harmless and survives adding choices later.

- [ ] **Step 7: Wire URL and sidebar**

`dashboard/urls.py` — add `inquiry_views` to the imports and:

```python
    path("inquiries", inquiry_views.InquiryListView.as_view(), name="inquiries"),
    path(
        "inquiries/<int:pk>/status",
        inquiry_views.InquiryStatusView.as_view(),
        name="inquiry_status",
    ),
```

`dashboard/templates/dashboard/_sidebar.html` — add this directly after the
Subscribers link (currently line 16-17). It is that element with the URL name,
`nav_active` argument and label changed, and a handshake icon in place of the
envelope:

```html
    <a href="{% url 'dashboard:inquiries' %}" class="sidebarLink {% nav_active request 'dashboard:inquiries' %}" @click="sidebarOpen = false">
      <svg class="sidebarIcon" width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M3 8.5l3-3 4 4 4-4 3 3v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>Inquiries</a>
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
.venv/bin/python manage.py test dashboard -v 1
```
Expected: PASS — including the pre-existing `test_smart_alerts` cases, which
must still pass unchanged because the new parameter has a default.

- [ ] **Step 9: Lint and commit**

```bash
.venv/bin/python -m flake8 dashboard/
git add dashboard/
git commit -m "feat(dashboard): sponsorship inquiry list and smart alert"
```

---

### Task 7: Fix placeholder `Screen.capacity`

Unrelated to sponsorships, but the tier-3 popcorn cap is aligned to a
100-seat house and both `Screen` rows currently claim to seat one person.

**Files:**
- Create: `cinema/screen_capacity.py`
- Create: `cinema/migrations/00XX_screen_capacity_backfill.py`
- Create: `cinema/tests/test_screen_capacity.py`

**Interfaces:**
- Consumes: `Screen` (existing).
- Produces: `cinema.screen_capacity.backfill_placeholder_capacity(manager) -> int` returning the number of rows changed.

A data migration cannot be unit-tested by importing it — migrations are not a
normal import path, and the test database is built by running them, so by the
time a test runs the backfill has already happened against an empty table. So
the *logic* lives in a plain function that both the migration and the test
call. That function is what gets tested; the migration is a one-line caller.

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_screen_capacity.py`:

```python
from cinema.models import Screen
from cinema.screen_capacity import PLACEHOLDER_CAPACITY, backfill_placeholder_capacity
from django.test import TestCase


class BackfillPlaceholderCapacityTests(TestCase):
    def test_replaces_placeholder_values(self):
        screen = Screen.objects.create(name="Placeholder", capacity=1)
        backfill_placeholder_capacity(Screen.objects)
        screen.refresh_from_db()
        self.assertEqual(screen.capacity, PLACEHOLDER_CAPACITY)

    def test_replaces_a_zero_capacity(self):
        screen = Screen.objects.create(name="Zero", capacity=0)
        backfill_placeholder_capacity(Screen.objects)
        screen.refresh_from_db()
        self.assertEqual(screen.capacity, PLACEHOLDER_CAPACITY)

    def test_leaves_a_real_seat_count_alone(self):
        # The guard that makes this safe to run on production.
        screen = Screen.objects.create(name="Real", capacity=248)
        backfill_placeholder_capacity(Screen.objects)
        screen.refresh_from_db()
        self.assertEqual(screen.capacity, 248)

    def test_returns_the_number_of_rows_changed(self):
        Screen.objects.create(name="A", capacity=1)
        Screen.objects.create(name="B", capacity=1)
        Screen.objects.create(name="C", capacity=248)
        self.assertEqual(backfill_placeholder_capacity(Screen.objects), 2)

    def test_is_idempotent(self):
        Screen.objects.create(name="A", capacity=1)
        backfill_placeholder_capacity(Screen.objects)
        self.assertEqual(backfill_placeholder_capacity(Screen.objects), 0)
```

- [ ] **Step 2: Write the backfill function**

Create `cinema/screen_capacity.py`:

```python
"""Repair placeholder Screen.capacity values.

Both screens shipped with capacity=1, which is not a seat count — it makes
any house-size reasoning nonsense, and the sponsorship program's Full House
tier is priced against a 100-seat room.

100 is the working figure until the seats are actually counted.

Lives here rather than inside the migration so it can be tested: a migration
runs while building the test database, against an empty table, so there is
nothing left for a test to observe by the time it runs.
"""

PLACEHOLDER_CAPACITY = 100


def backfill_placeholder_capacity(manager) -> int:
    """Set every placeholder capacity to PLACEHOLDER_CAPACITY.

    `manager` is Screen.objects, or the historical model's manager when
    called from a migration. Guarded to capacity <= 1 so a real seat count
    that production may already carry is never clobbered.

    Returns the number of rows changed.
    """
    return manager.filter(capacity__lte=1).update(capacity=PLACEHOLDER_CAPACITY)
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `.venv/bin/python manage.py test cinema.tests.test_screen_capacity -v 2`
Expected: PASS (all five)

- [ ] **Step 4: Write the migration**

Create the migration by hand (replace `00XX` with the next number, and
`00YY_...` with the actual latest cinema migration name):

```python
"""Backfill placeholder Screen.capacity values.

The logic lives in cinema/screen_capacity.py so it can be tested; see the
docstring there for why.
"""

from cinema.screen_capacity import backfill_placeholder_capacity
from django.db import migrations


def backfill(apps, schema_editor):
    Screen = apps.get_model("cinema", "Screen")
    backfill_placeholder_capacity(Screen.objects)


def unbackfill(apps, schema_editor):
    # Deliberately a no-op: reverting to capacity=1 would restore bad data.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cinema", "00YY_previous_migration_name"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
```

Find the real value for `00YY_previous_migration_name` with:

```bash
ls cinema/migrations/ | grep -E '^[0-9]' | sort | tail -1
```

- [ ] **Step 5: Apply and verify**

```bash
.venv/bin/python manage.py migrate cinema
.venv/bin/python manage.py shell -c \
  "from cinema.models import Screen; print([(s.name, s.capacity) for s in Screen.objects.all()])"
```
Expected: `[('The Century', 100), ('The Savoy', 100)]`

- [ ] **Step 6: Run the tests**

```bash
.venv/bin/python manage.py test cinema -v 1
```
Expected: PASS

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/python -m flake8 cinema/
git add cinema/screen_capacity.py cinema/migrations/ cinema/tests/test_screen_capacity.py
git commit -m "fix(cinema): backfill placeholder Screen.capacity values"
```

---

### Task 8: Full verification

**Files:** none created — this is the gate before the branch is done.

- [ ] **Step 1: Run the entire test suite**

```bash
.venv/bin/python manage.py test -v 1
```
Expected: PASS, zero failures, zero errors. Report the actual counts.

- [ ] **Step 2: Lint**

**Do not run `flake8 .`** — `.flake8` excludes `.git,__pycache__,build,dist,*/migrations/*`
but **not `.venv`**, so a bare `.` scans the virtualenv and reports ~36,800
violations that have nothing to do with this project.

This repo also carries a **pre-existing baseline of 274 violations** across its
app directories (web 47, cinema 39, dashboard 173, blog 14, fortkentcinema 1),
measured on `main`. Fixing those is out of scope for this branch.

So there are two checks. First, the branch's own files must be clean:

```bash
git diff --name-only <MERGE_BASE>..HEAD -- '*.py' \
  | grep -v migrations \
  | tr '\n' '\0' | xargs -0 .venv/bin/python -m flake8
```

Expected: **only pre-existing E501 lines** in `web/constants.py` (membership FAQ
answers), `web/urls.py` (the About-page comment) and `web/views.py` (a blog
query and a runtime-ISO line) — all eight of which exist identically on `main`.
No violation may point at a line this branch wrote.

Second, the app-wide total must not have grown:

```bash
.venv/bin/python -m flake8 web cinema dashboard blog audience cms fortkentcinema | wc -l
```

Expected: **274**. A higher number means this branch added violations; find and
fix them. (`xargs -a` is GNU-only and fails on macOS — use the `tr | xargs -0`
form above.)

- [ ] **Step 3: Confirm the CSS bundle is current**

```bash
cd frontend && npm run build && cd .. && git status --short static/
```
Expected: no unstaged change to `static/css/bundle.css` — if there is one, the
bundle was stale; commit it.

- [ ] **Step 4: Eyeball the real page**

```bash
.venv/bin/python manage.py runserver
```
Visit `http://127.0.0.1:8000/sponsor/` and confirm: the table shows real
Universal titles, search for "jurassic" narrows it, the decade filter works,
pagination moves between pages, and the tiers read $299 / $499 / $799.

- [ ] **Step 5: Report**

State plainly what passed and what did not. Do not claim mypy or black ran —
they are not gates in this project.
