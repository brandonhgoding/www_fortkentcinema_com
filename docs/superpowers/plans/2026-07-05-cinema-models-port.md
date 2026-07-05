# Cinema Models Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the leprinceos showtimes/engagements domain models into a single new `cinema` app in `api_fortkentcinema_com`, with a Django admin that uses inlines for the Engagement relations.

**Architecture:** One consolidated Django app (`cinema`) holds `Film`, `Screen`, `Engagement`, `EngagementFilm`, `Showtime` — a verbatim field/constraint port of the four leprinceos apps, with cross-app references rewritten to the single `cinema` app label. Admin registers each model, and the Engagement admin nests `EngagementFilm` and `Showtime` as `TabularInline`s. Empty tables; no data import; frontend untouched.

**Tech Stack:** Django 5.2, Python 3.13, `manage.py test` (Django `unittest` / `TestCase`).

## Global Constraints

- Models are a **verbatim** port of leprinceos: keep every field, choice, index, `UniqueConstraint`, property, and `save()`/`clean()` method unchanged. The only edits are the four-apps→one-app reference rewrites.
- App label is `cinema`. All intra-model FK/M2M string references use the `cinema.` prefix.
- `SiteConfig` is **not** ported. `Genre` is **not** ported.
- Tests use `django.test.TestCase`, run with `python manage.py test cinema`. Test files live in `cinema/tests/`.
- Type hints are used throughout (match existing `blog`/`web` style, e.g. `-> None`).
- Do not modify `web/`, `blog/`, or `web/services/leprinceos.py`. The only non-`cinema` file touched is `fortkentcinema/settings.py` (INSTALLED_APPS).
- Run all commands from the repo root `api_fortkentcinema_com/` with the venv active: `source .venv/bin/activate`.

---

### Task 1: Scaffold the `cinema` app and register it

**Files:**
- Create: `cinema/__init__.py` (empty)
- Create: `cinema/apps.py`
- Create: `cinema/models/__init__.py` (empty for now)
- Create: `cinema/migrations/__init__.py` (empty)
- Create: `cinema/tests/__init__.py` (empty)
- Modify: `fortkentcinema/settings.py` (INSTALLED_APPS)

**Interfaces:**
- Produces: an installed Django app with label `cinema` and no models yet.

- [ ] **Step 1: Create the app package files**

`cinema/__init__.py` — empty file.

`cinema/apps.py`:

```python
from django.apps import AppConfig


class CinemaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cinema"
```

`cinema/models/__init__.py` — empty file (models added in later tasks).

`cinema/migrations/__init__.py` — empty file.

`cinema/tests/__init__.py` — empty file.

- [ ] **Step 2: Register the app in settings**

In `fortkentcinema/settings.py`, add `"cinema.apps.CinemaConfig"` to `INSTALLED_APPS` immediately after `"web.apps.WebConfig"`:

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "blog.apps.BlogConfig",
    "web.apps.WebConfig",
    "cinema.apps.CinemaConfig",
    "rest_framework",
    "corsheaders",
]
```

- [ ] **Step 3: Verify the app loads**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add cinema/ fortkentcinema/settings.py
git commit -m "feat(cinema): scaffold cinema app and register in INSTALLED_APPS"
```

---

### Task 2: Film model

**Files:**
- Create: `cinema/models/film.py`
- Modify: `cinema/models/__init__.py`
- Create/Modify: `cinema/tests/test_models.py`
- Create: `cinema/migrations/0001_initial.py` (generated)

**Interfaces:**
- Produces: `cinema.models.Film` with fields `title`, `runtime_minutes`, `rating`, `synopsis`, `poster_url`, `backdrop_url`, `overview`, `tmdb_id`, `imdb_id`, `youtube_id`, `created_at`; `save()` coerces empty-string external ids to `None`; ordered by `title`.

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_models.py`:

```python
from cinema.models import Film
from django.test import TestCase


class FilmTestCase(TestCase):
    def test_str_is_title(self) -> None:
        film = Film.objects.create(title="Toy Story 5")
        self.assertEqual(str(film), "Toy Story 5")

    def test_blank_external_ids_coerced_to_none(self) -> None:
        # Empty-string ids must become NULL so multiple blank films are allowed
        # under the unique constraints on tmdb_id/imdb_id/youtube_id.
        first = Film.objects.create(title="A", tmdb_id="", imdb_id="", youtube_id="")
        second = Film.objects.create(title="B", tmdb_id="", imdb_id="", youtube_id="")
        first.refresh_from_db()
        self.assertIsNone(first.tmdb_id)
        self.assertIsNone(second.tmdb_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_models -v 2`
Expected: FAIL — `ImportError`/`ModuleNotFoundError` (cannot import `Film`).

- [ ] **Step 3: Write the model**

Create `cinema/models/film.py`:

```python
# cinema/models/film.py
from typing import Any

from django.db import models


class Film(models.Model):
    """
    Film in the system catalog.
    """

    title = models.CharField(max_length=200)
    runtime_minutes = models.PositiveIntegerField(null=True, blank=True)
    rating = models.CharField(max_length=10, blank=True)
    synopsis = models.TextField(blank=True)
    poster_url = models.URLField(blank=True)
    backdrop_url = models.URLField(blank=True)
    overview = models.TextField(blank=True)

    tmdb_id = models.CharField(max_length=50, blank=True, unique=True, null=True)
    imdb_id = models.CharField(max_length=50, blank=True, unique=True, null=True)
    youtube_id = models.CharField(max_length=50, blank=True, unique=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Convert empty string to None for unique constraint
        if self.tmdb_id == "":
            self.tmdb_id = None
        if self.imdb_id == "":
            self.imdb_id = None
        if self.youtube_id == "":
            self.youtube_id = None
        super().save(*args, **kwargs)
```

Set `cinema/models/__init__.py` to:

```python
from .film import Film

__all__ = ["Film"]
```

- [ ] **Step 4: Generate and apply the migration**

Run: `python manage.py makemigrations cinema`
Expected: creates `cinema/migrations/0001_initial.py` with the `Film` model.

Run: `python manage.py migrate cinema`
Expected: applies `cinema.0001_initial` without error.

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test cinema.tests.test_models -v 2`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add cinema/models/ cinema/tests/test_models.py cinema/migrations/0001_initial.py
git commit -m "feat(cinema): add Film model"
```

---

### Task 3: Screen model

**Files:**
- Create: `cinema/models/screen.py`
- Modify: `cinema/models/__init__.py`
- Modify: `cinema/tests/test_models.py`
- Create: `cinema/migrations/0002_screen.py` (generated)

**Interfaces:**
- Produces: `cinema.models.Screen` with `name`, `capacity`, `screen_type`, `aspect_ratio`, `sound_system`, `supports_3d`; ordered by `name`.

- [ ] **Step 1: Write the failing test**

Append to `cinema/tests/test_models.py`:

```python
from cinema.models import Screen  # add to imports at top of file


class ScreenTestCase(TestCase):
    def test_str_is_name(self) -> None:
        screen = Screen.objects.create(name="Screen 1", capacity=120)
        self.assertEqual(str(screen), "Screen 1")

    def test_defaults(self) -> None:
        screen = Screen.objects.create(name="Main", capacity=200)
        self.assertEqual(screen.screen_type, "standard")
        self.assertEqual(screen.aspect_ratio, "scope")
        self.assertEqual(screen.sound_system, "standard")
        self.assertFalse(screen.supports_3d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_models.ScreenTestCase -v 2`
Expected: FAIL — cannot import `Screen`.

- [ ] **Step 3: Write the model**

Create `cinema/models/screen.py`:

```python
# cinema/models/screen.py
from django.db import models


class Screen(models.Model):
    name = models.CharField(max_length=100)  # "Screen 1", "Main", etc.
    capacity = models.PositiveIntegerField()

    SCREEN_TYPES = [
        ("standard", "Standard"),
        ("imax", "IMAX"),
        ("dolby_cinema", "Dolby Cinema"),
    ]
    screen_type = models.CharField(
        choices=SCREEN_TYPES, default="standard", max_length=12
    )

    ASPECT_RATIOS = [
        ("flat", "Flat (1.85:1)"),
        ("scope", "Scope (2.39:1)"),
        ("imax_190", "IMAX 1.90:1"),
        ("imax_143", "IMAX 1.43:1"),
    ]
    aspect_ratio = models.CharField(
        choices=ASPECT_RATIOS, max_length=8, default="scope"
    )

    SOUND_SYSTEMS = [
        ("standard", "Standard Surround"),
        ("dolby_digital", "Dolby Digital"),
        ("dolby_atmos", "Dolby Atmos"),
    ]
    sound_system = models.CharField(
        choices=SOUND_SYSTEMS, max_length=13, default="standard"
    )

    supports_3d = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
```

Update `cinema/models/__init__.py`:

```python
from .film import Film
from .screen import Screen

__all__ = ["Film", "Screen"]
```

- [ ] **Step 4: Generate and apply the migration**

Run: `python manage.py makemigrations cinema`
Expected: creates `cinema/migrations/0002_screen.py`.

Run: `python manage.py migrate cinema`
Expected: applies without error.

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test cinema.tests.test_models -v 2`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add cinema/models/ cinema/tests/test_models.py cinema/migrations/0002_screen.py
git commit -m "feat(cinema): add Screen model"
```

---

### Task 4: Engagement + EngagementFilm models

**Files:**
- Create: `cinema/models/engagement.py`
- Create: `cinema/models/engagement_film.py`
- Modify: `cinema/models/__init__.py`
- Modify: `cinema/tests/test_models.py`
- Create: `cinema/migrations/0003_*.py` (generated)

**Interfaces:**
- Consumes: `cinema.models.Film`, `cinema.models.Screen`.
- Produces:
  - `cinema.models.Engagement` — FK `screen` (PROTECT, related_name `engagements`), M2M `films` through `cinema.EngagementFilm` (related_name `engagements`), `start_date`, `end_date`, `presentation_format`, `kind`, `event_title`, `show_in_main_listings`, `status`, `notes`, `created_at`; properties `display_title`, `is_active`, `is_free_for_members`, `ordered_films`, `primary_film`, `total_runtime_minutes`; `clean()` rejects `end_date < start_date`; classmethod `default_visibility_for(kind)`. Module-level `EngagementStatus` TextChoices.
  - `cinema.models.EngagementFilm` — FK `engagement` (`cinema.Engagement`, CASCADE, related_name `engagement_films`), FK `film` (PROTECT, related_name `engagement_films`), `position`; unique `(engagement, position)` and `(engagement, film)`; ordered by `position`.

- [ ] **Step 1: Write the failing test**

Append to `cinema/tests/test_models.py`:

```python
import datetime

from cinema.models import Engagement, EngagementFilm  # add to top imports
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction


class EngagementTestCase(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film_a = Film.objects.create(title="Alpha", runtime_minutes=90)
        self.film_b = Film.objects.create(title="Beta", runtime_minutes=100)

    def _engagement(self, **kwargs) -> Engagement:
        defaults = dict(
            screen=self.screen,
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
        )
        defaults.update(kwargs)
        return Engagement.objects.create(**defaults)

    def test_display_title_from_films_in_position_order(self) -> None:
        eng = self._engagement()
        EngagementFilm.objects.create(engagement=eng, film=self.film_b, position=2)
        EngagementFilm.objects.create(engagement=eng, film=self.film_a, position=1)
        self.assertEqual(eng.display_title, "Alpha + Beta")
        self.assertEqual([f.title for f in eng.ordered_films], ["Alpha", "Beta"])
        self.assertEqual(eng.primary_film, self.film_a)
        self.assertEqual(eng.total_runtime_minutes, 190)

    def test_event_title_overrides_display_title(self) -> None:
        eng = self._engagement(event_title="Summer Double Feature")
        self.assertEqual(eng.display_title, "Summer Double Feature")

    def test_clean_rejects_end_before_start(self) -> None:
        eng = Engagement(
            screen=self.screen,
            start_date=datetime.date(2026, 7, 7),
            end_date=datetime.date(2026, 7, 1),
        )
        with self.assertRaises(ValidationError):
            eng.clean()

    def test_unique_engagement_position(self) -> None:
        eng = self._engagement()
        EngagementFilm.objects.create(engagement=eng, film=self.film_a, position=1)
        # Wrap the failing INSERT in atomic() so the broken transaction is
        # contained and TestCase teardown can still roll back cleanly.
        with self.assertRaises(IntegrityError), transaction.atomic():
            EngagementFilm.objects.create(engagement=eng, film=self.film_b, position=1)

    def test_is_free_for_members_by_kind(self) -> None:
        self.assertTrue(self._engagement(kind=Engagement.Kind.CLASSIC).is_free_for_members)
        self.assertFalse(self._engagement(kind=Engagement.Kind.REGULAR).is_free_for_members)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_models.EngagementTestCase -v 2`
Expected: FAIL — cannot import `Engagement`/`EngagementFilm`.

- [ ] **Step 3: Write the models**

Create `cinema/models/engagement.py`:

```python
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Manager
from django.utils import timezone

from .film import Film
from .screen import Screen


class EngagementStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"
    CANCELLED = "CANCELLED", "Cancelled"
    ENDED = "ENDED", "Ended"


class Engagement(models.Model):
    objects: ClassVar[Manager["Engagement"]]

    films = models.ManyToManyField(
        Film, through="cinema.EngagementFilm", related_name="engagements"
    )
    # screen = intended/default screen for this run
    screen = models.ForeignKey(
        Screen, on_delete=models.PROTECT, related_name="engagements"
    )

    start_date = models.DateField()
    end_date = models.DateField()

    FORMAT_CHOICES = [
        ("2d", "2D"),
        ("3d", "3D"),
    ]
    presentation_format = models.CharField(
        max_length=2,
        choices=FORMAT_CHOICES,
        default="2d",
    )

    class Kind(models.TextChoices):
        REGULAR = "REGULAR", "Regular"
        SPECIAL_EVENT = "SPECIAL_EVENT", "Special Event"
        CLASSIC = "CLASSIC", "Classic"
        DOUBLE_FEATURE = "DOUBLE_FEATURE", "Double Feature"

    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.REGULAR
    )
    event_title = models.CharField(max_length=200, blank=True)
    show_in_main_listings = models.BooleanField(default=True)

    # TODO: Validation that an 3d engagement can't be book on non 3d screens

    status = models.CharField(
        max_length=20, choices=EngagementStatus.choices, default=EngagementStatus.DRAFT
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date"]
        indexes = [
            models.Index(fields=["start_date", "end_date"]),
        ]
        verbose_name = "Engagement"
        verbose_name_plural = "Engagements"

    def __str__(self) -> str:
        return f"{self.display_title} ({self.start_date} → {self.end_date})"

    @property
    def is_free_for_members(self) -> bool:
        if self.kind in [self.Kind.CLASSIC, self.Kind.DOUBLE_FEATURE, self.Kind.SPECIAL_EVENT]:
            return True
        return False

    @property
    def is_active(self) -> bool:
        today = timezone.localdate()
        return (
            self.status == EngagementStatus.CONFIRMED
            and self.start_date <= today <= self.end_date
        )

    @property
    def ordered_films(self) -> list[Film]:
        return [ef.film for ef in self.engagement_films.all()]

    @property
    def primary_film(self) -> Film | None:
        films = self.ordered_films
        return films[0] if films else None

    @property
    def total_runtime_minutes(self) -> int:
        return sum((f.runtime_minutes or 0) for f in self.ordered_films)

    @property
    def display_title(self) -> str:
        if self.event_title:
            return self.event_title
        return " + ".join(f.title for f in self.ordered_films)

    def clean(self) -> None:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("end_date cannot be before start_date.")

    @classmethod
    def default_visibility_for(cls, kind: str) -> bool:
        return kind == cls.Kind.REGULAR
```

Create `cinema/models/engagement_film.py`:

```python
# cinema/models/engagement_film.py
from typing import ClassVar

from django.db import models
from django.db.models import Manager

from .film import Film


class EngagementFilm(models.Model):
    objects: ClassVar[Manager["EngagementFilm"]]

    engagement = models.ForeignKey(
        "cinema.Engagement",
        on_delete=models.CASCADE,
        related_name="engagement_films",
    )
    film = models.ForeignKey(
        Film, on_delete=models.PROTECT, related_name="engagement_films"
    )
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "position"],
                name="unique_engagement_position",
            ),
            models.UniqueConstraint(
                fields=["engagement", "film"],
                name="unique_engagement_film",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.engagement_id}: {self.film.title} (#{self.position})"
```

Update `cinema/models/__init__.py`:

```python
from .engagement import Engagement, EngagementStatus
from .engagement_film import EngagementFilm
from .film import Film
from .screen import Screen

__all__ = ["Film", "Screen", "Engagement", "EngagementStatus", "EngagementFilm"]
```

- [ ] **Step 4: Generate and apply the migration**

Run: `python manage.py makemigrations cinema`
Expected: creates `cinema/migrations/0003_engagement_engagementfilm.py` (name may vary).

Run: `python manage.py migrate cinema`
Expected: applies without error.

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test cinema.tests.test_models -v 2`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add cinema/models/ cinema/tests/test_models.py cinema/migrations/
git commit -m "feat(cinema): add Engagement and EngagementFilm models"
```

---

### Task 5: Showtime model

**Files:**
- Create: `cinema/models/showtime.py`
- Modify: `cinema/models/__init__.py`
- Modify: `cinema/tests/test_models.py`
- Create: `cinema/migrations/0004_showtime.py` (generated)

**Interfaces:**
- Consumes: `cinema.models.Engagement`, `cinema.models.Screen`.
- Produces: `cinema.models.Showtime` — FK `engagement` (CASCADE, related_name `showtimes`), FK `screen` (PROTECT, related_name `showtimes`), `starts_at`, `is_cancelled`, `captions` (CC/OC choices, nullable); `save()` defaults `screen_id` from the engagement when unset; property `is_outside_engagement_range`; unique `(screen, starts_at)`; ordered by `starts_at`.

- [ ] **Step 1: Write the failing test**

Append to `cinema/tests/test_models.py`:

```python
from cinema.models import Showtime  # add to top imports
from django.db import transaction  # if not already imported at top
from django.utils import timezone as dj_timezone


class ShowtimeTestCase(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.other_screen = Screen.objects.create(name="Screen 2", capacity=80)
        self.film = Film.objects.create(title="Alpha", runtime_minutes=90)
        self.eng = Engagement.objects.create(
            screen=self.screen,
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
        )
        EngagementFilm.objects.create(engagement=self.eng, film=self.film, position=1)

    def _dt(self, day: int, hour: int) -> datetime.datetime:
        return dj_timezone.make_aware(datetime.datetime(2026, 7, day, hour, 0))

    def test_save_defaults_screen_from_engagement(self) -> None:
        showtime = Showtime(engagement=self.eng, starts_at=self._dt(2, 19))
        showtime.save()
        self.assertEqual(showtime.screen_id, self.screen.id)

    def test_save_keeps_explicit_screen(self) -> None:
        showtime = Showtime.objects.create(
            engagement=self.eng, screen=self.other_screen, starts_at=self._dt(2, 19)
        )
        self.assertEqual(showtime.screen_id, self.other_screen.id)

    def test_unique_screen_starts_at(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=self._dt(2, 19))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Showtime.objects.create(engagement=self.eng, starts_at=self._dt(2, 19))

    def test_is_outside_engagement_range(self) -> None:
        inside = Showtime.objects.create(engagement=self.eng, starts_at=self._dt(3, 19))
        outside = Showtime.objects.create(engagement=self.eng, starts_at=self._dt(9, 19))
        self.assertFalse(inside.is_outside_engagement_range)
        self.assertTrue(outside.is_outside_engagement_range)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_models.ShowtimeTestCase -v 2`
Expected: FAIL — cannot import `Showtime`.

- [ ] **Step 3: Write the model**

Create `cinema/models/showtime.py`:

```python
from typing import Any, ClassVar

from django.db import models
from django.db.models import Manager

from .engagement import Engagement
from .screen import Screen


class Showtime(models.Model):
    objects: ClassVar[Manager["Showtime"]]

    class CaptionChoices(models.TextChoices):
        cc = "CC", "Closed Captions"
        oc = "OC", "Open Captions"

    # Type hints for ForeignKey _id attributes (set by Django at runtime)
    engagement_id: int | None
    screen_id: int | None

    engagement = models.ForeignKey(
        Engagement, on_delete=models.CASCADE, related_name="showtimes"
    )
    # screen = actual screen for this specific performance
    screen = models.ForeignKey(
        Screen, on_delete=models.PROTECT, related_name="showtimes"
    )

    starts_at = models.DateTimeField()

    is_cancelled = models.BooleanField(default=False)
    captions = models.CharField(
        null=True,
        blank=True,
        default=None,
        max_length=2,
        choices=CaptionChoices.choices,
    )

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["engagement", "starts_at"]),
            models.Index(fields=["screen", "is_cancelled", "starts_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["screen", "starts_at"],
                name="unique_screen_starts_at",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.engagement.display_title} @ {self.starts_at}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.engagement_id:
            if not self.screen_id:
                self.screen_id = self.engagement.screen_id
        super().save(*args, **kwargs)

    def clean(self) -> None:
        # Date range validation is now a soft warning, not a hard constraint.
        pass

    @property
    def is_outside_engagement_range(self) -> bool:
        """Check if showtime falls outside engagement date range (for warnings)."""
        if not self.engagement_id or not self.starts_at:
            return False
        show_date = self.starts_at.date()
        return bool(
            show_date < self.engagement.start_date
            or show_date > self.engagement.end_date
        )
```

Update `cinema/models/__init__.py`:

```python
from .engagement import Engagement, EngagementStatus
from .engagement_film import EngagementFilm
from .film import Film
from .screen import Screen
from .showtime import Showtime

__all__ = [
    "Film",
    "Screen",
    "Engagement",
    "EngagementStatus",
    "EngagementFilm",
    "Showtime",
]
```

- [ ] **Step 4: Generate and apply the migration**

Run: `python manage.py makemigrations cinema`
Expected: creates `cinema/migrations/0004_showtime.py`.

Run: `python manage.py migrate cinema`
Expected: applies without error.

- [ ] **Step 5: Run the full model test suite**

Run: `python manage.py test cinema.tests.test_models -v 2`
Expected: PASS (all model tests across Film, Screen, Engagement, Showtime).

- [ ] **Step 6: Commit**

```bash
git add cinema/models/ cinema/tests/test_models.py cinema/migrations/0004_showtime.py
git commit -m "feat(cinema): add Showtime model"
```

---

### Task 6: Django admin with inlines

**Files:**
- Create: `cinema/admin.py`
- Create: `cinema/tests/test_admin.py`

**Interfaces:**
- Consumes: all `cinema.models`.
- Produces: admin registrations for `Film`, `Screen`, `Showtime`, `Engagement`; `EngagementAdmin` nests `EngagementFilmInline` and `ShowtimeInline`.

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_admin.py`:

```python
from cinema.admin import EngagementAdmin, EngagementFilmInline, ShowtimeInline
from cinema.models import Engagement, Film, Screen, Showtime
from django.contrib import admin
from django.test import TestCase


class CinemaAdminTestCase(TestCase):
    def test_models_registered(self) -> None:
        for model in (Film, Screen, Showtime, Engagement):
            self.assertIn(model, admin.site._registry)

    def test_engagement_admin_has_inlines(self) -> None:
        engagement_admin = admin.site._registry[Engagement]
        self.assertIsInstance(engagement_admin, EngagementAdmin)
        self.assertIn(EngagementFilmInline, engagement_admin.inlines)
        self.assertIn(ShowtimeInline, engagement_admin.inlines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_admin -v 2`
Expected: FAIL — cannot import from `cinema.admin`.

- [ ] **Step 3: Write the admin**

Create `cinema/admin.py`:

```python
# cinema/admin.py
# mypy: disable-error-code="type-arg"
from django.contrib import admin

from .models import Engagement, EngagementFilm, Film, Screen, Showtime


class EngagementFilmInline(admin.TabularInline):
    model = EngagementFilm
    extra = 1
    ordering = ("position",)


class ShowtimeInline(admin.TabularInline):
    model = Showtime
    extra = 0


@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    inlines = (EngagementFilmInline, ShowtimeInline)
    list_display = (
        "display_title",
        "screen",
        "start_date",
        "end_date",
        "status",
        "presentation_format",
    )
    list_filter = ("status", "presentation_format")
    search_fields = ("engagement_films__film__title",)
    date_hierarchy = "start_date"


@admin.register(Showtime)
class ShowtimeAdmin(admin.ModelAdmin):
    list_display = (
        "engagement",
        "screen",
        "starts_at",
        "is_cancelled",
        "captions",
    )
    list_filter = ("screen", "is_cancelled", "captions")
    search_fields = ("engagement__engagement_films__film__title",)
    date_hierarchy = "starts_at"


@admin.register(Film)
class FilmAdmin(admin.ModelAdmin):
    list_display = ("title", "rating", "runtime_minutes", "created_at")
    search_fields = ("title", "tmdb_id", "imdb_id")
    list_filter = ("rating",)


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity")
```

Note: the source `ShowtimeAdmin.search_fields` used `engagement__film__title`, which is not a valid lookup (there is no direct `film` relation on Engagement). It is corrected here to `engagement__engagement_films__film__title` to traverse the through-model.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test cinema.tests.test_admin -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Run Django's admin system checks**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).` (validates `list_display`/`search_fields`/inline config.)

- [ ] **Step 6: Commit**

```bash
git add cinema/admin.py cinema/tests/test_admin.py
git commit -m "feat(cinema): admin with EngagementFilm and Showtime inlines"
```

---

### Task 7: Final verification

**Files:** none (verification only).

- [ ] **Step 1: Confirm migrations are complete and consistent**

Run: `python manage.py makemigrations --check --dry-run`
Expected: `No changes detected` (all model state is captured in migrations).

- [ ] **Step 2: Run the full cinema test suite**

Run: `python manage.py test cinema -v 2`
Expected: PASS (all model + admin tests).

- [ ] **Step 3: Run the whole project test suite (no regressions)**

Run: `python manage.py test`
Expected: PASS — the existing `blog`/`web` suites still pass; new `cinema` tests included.

- [ ] **Step 4: Manual admin smoke check (optional but recommended)**

Run: `python manage.py runserver`, log into `/admin` (or the project's admin URL), and confirm:
- Create a `Screen` and a `Film`.
- Create an `Engagement`; add the film via the **EngagementFilm inline** (set position) and add a **Showtime inline** with no screen — save and confirm the showtime's screen defaulted to the engagement's screen, and the engagement `display_title` shows the film title.

---

## Self-Review

**Spec coverage:**
- Consolidated `cinema` app → Task 1. ✅
- `Film`, `Screen`, `Engagement`, `EngagementFilm`, `Showtime` verbatim → Tasks 2–5. ✅
- `SiteConfig`/`Genre` dropped → not present in any task. ✅
- Reference rewrites (`cinema.EngagementFilm`, `cinema.Engagement`, intra-app imports) → Task 4/5 code. ✅
- Admin with EngagementFilm + Showtime inlines, standalone Film/Screen/Showtime → Task 6. ✅
- INSTALLED_APPS wiring + migrations + empty tables → Tasks 1–7. ✅
- Frontend / leprinceos service untouched → enforced by Global Constraints; no task edits `web/`. ✅
- Verification (makemigrations --check, migrate, check, admin smoke) → Task 7 + inline steps. ✅

**Placeholder scan:** No TBD/TODO-as-instruction; all code shown in full. (The single `# TODO` inside `Engagement` is verbatim source content, intentionally preserved, not a plan placeholder.)

**Type consistency:** `EngagementFilm.engagement` related_name `engagement_films` is used by `Engagement.ordered_films`, `search_fields`, and the corrected `ShowtimeAdmin.search_fields`. `Showtime.screen_id`/`engagement_id` used in `save()` match the FK field names. Inline class names `EngagementFilmInline`/`ShowtimeInline` match between Task 6 code and its test.
