# Social Card Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Social Images" panel to the dashboard engagement detail page that renders Facebook (1200×630) and Instagram (1080×1080) promo PNGs in the Fort Kent Cinema thumbnail theme, with a Coming Soon / Now Playing toggle.

**Architecture:** A new `cinema/social_cards/` package renders the images server-side with Pillow. It is layered: `theme.py` holds constants, `card.py` turns an `Engagement` into pure text/URL data with no Pillow involved, `posters.py` fetches artwork over HTTP, `draw.py` provides drawing primitives that know nothing about engagements, and `layouts.py` composes them onto a canvas. A single staff-only dashboard view serves the PNG inline (for the preview) or as an attachment (for the download buttons).

**Tech Stack:** Django 5.2, Pillow 11.2, `requests`, Alpine.js (already loaded on every dashboard page), Django `TestCase`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-31-social-card-export-design.md`. Read it before starting.
- **No new Python dependencies.** Pillow and `requests` are already in `requirements.txt`.
- **mypy is strict** (`disallow_untyped_defs = True`). Every function and method, **including test methods**, needs type annotations. Test methods are annotated `-> None`.
- **Line length is 88** (black + flake8). `extend-ignore = E203, W503`.
- **Tests run with** `.venv/bin/python manage.py test <dotted.path>`. There is no pytest in this project.
- **No test may touch the network.** All artwork fetches are mocked.
- **Exact fixed copy**, uppercase, used verbatim:
  - Wordmark: `FORT KENT CINEMA`
  - Footer: `VISIT WWW.FORTKENTCINEMA.COM FOR SHOWTIMES`
  - Badges: `NOW PLAYING`, `COMING SOON`
- **Platform identifiers** are the lowercase strings `facebook` and `instagram`.
- **Badge query-param values** are `now_playing` and `coming_soon` (underscores). **Badge filename slugs** are `now-playing` and `coming-soon` (hyphens). These are deliberately different — do not conflate them.
- **Determinism:** no `random`, no `datetime.now()` inside rendering. Anything date-dependent takes an injectable `today` argument.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `cinema/social_cards/__init__.py` | Public entry point: `render_card()`, `card_filename()`. Wires the layers together. |
| `cinema/social_cards/theme.py` | Palette, canvas sizes, font paths, glow radii, cached font loader. |
| `cinema/social_cards/fonts/` | Vendored `Poppins-ExtraBold.ttf`, `Poppins-SemiBold.ttf`, `OFL.txt`. |
| `cinema/social_cards/card.py` | `CardData`, `Artwork`, badge/date/headline/artwork rules. No Pillow import. |
| `cinema/social_cards/posters.py` | `upsize_tmdb_url()`, `fetch_artwork()`. HTTP + cache + decode guards. |
| `cinema/social_cards/draw.py` | Primitives: background, trees, bulbs, text fitting, glow text, cover-crop, edge fade, dashed frame. Knows nothing about engagements. |
| `cinema/social_cards/layouts.py` | `render()` — geometry and composition for both platforms. |
| `cinema/tests/test_social_cards_card.py` | Content-rule tests (Task 2). |
| `cinema/tests/test_social_cards_posters.py` | Fetch/cache/guard tests (Task 3). |
| `cinema/tests/test_social_cards_draw.py` | Primitive tests (Tasks 4–5). |
| `cinema/tests/test_social_cards_layouts.py` | Render smoke tests (Task 6). |
| `dashboard/views.py` | New `EngagementSocialCardView`; `EngagementDetailView` gains three context keys. |
| `dashboard/urls.py` | New route. |
| `dashboard/templates/dashboard/_social_cards.html` | The panel. |
| `dashboard/static/dashboard/css/social_cards.css` | Panel styles. |
| `dashboard/tests/test_social_cards.py` | View + panel tests (Tasks 7–8). |

---

### Task 1: Theme constants and vendored fonts

Pillow cannot read the `.woff2` files in `static/fonts/`, so real `.ttf` files must live in the repo. Poppins is under the SIL Open Font License, which permits redistribution as long as the licence travels with the fonts.

**Files:**
- Create: `cinema/social_cards/__init__.py` (empty for now)
- Create: `cinema/social_cards/theme.py`
- Create: `cinema/social_cards/fonts/Poppins-ExtraBold.ttf` (downloaded)
- Create: `cinema/social_cards/fonts/Poppins-SemiBold.ttf` (downloaded)
- Create: `cinema/social_cards/fonts/OFL.txt` (downloaded)
- Test: `cinema/tests/test_social_cards_theme.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `theme.FONT_BOLD: str`, `theme.FONT_MEDIUM: str` — absolute paths as strings
  - `theme.load_font(path: str, size: int) -> ImageFont.FreeTypeFont`
  - `theme.INK`, `theme.INK_CENTRE`, `theme.INK_EDGE`, `theme.GOLD`, `theme.CREAM` — `tuple[int, int, int]`
  - `theme.FACEBOOK_SIZE: tuple[int, int]`, `theme.INSTAGRAM_SIZE: tuple[int, int]`
  - `theme.GLOW_TIGHT_RADIUS: int`, `theme.GLOW_WIDE_RADIUS: int`

- [ ] **Step 1: Create the package and download the fonts**

```bash
mkdir -p cinema/social_cards/fonts
touch cinema/social_cards/__init__.py

BASE=https://github.com/google/fonts/raw/main/ofl/poppins
curl -sL "$BASE/Poppins-ExtraBold.ttf" -o cinema/social_cards/fonts/Poppins-ExtraBold.ttf
curl -sL "$BASE/Poppins-SemiBold.ttf"  -o cinema/social_cards/fonts/Poppins-SemiBold.ttf
curl -sL "$BASE/OFL.txt"               -o cinema/social_cards/fonts/OFL.txt

ls -l cinema/social_cards/fonts/
```

Each `.ttf` should be roughly 150–170 KB. If either file is under 10 KB you downloaded an HTML error page — stop and re-check the URL.

- [ ] **Step 2: Write the failing test**

Create `cinema/tests/test_social_cards_theme.py`:

```python
from pathlib import Path

from django.test import TestCase

from cinema.social_cards import theme


class ThemeTests(TestCase):
    def test_font_files_are_present_and_real(self) -> None:
        for path in (theme.FONT_BOLD, theme.FONT_MEDIUM):
            size = Path(path).stat().st_size
            self.assertGreater(size, 10_000, f"{path} looks like an error page")

    def test_licence_ships_with_the_fonts(self) -> None:
        licence = Path(theme.FONT_BOLD).parent / "OFL.txt"
        self.assertIn("SIL OPEN FONT LICENSE", licence.read_text().upper())

    def test_load_font_returns_font_at_requested_size(self) -> None:
        font = theme.load_font(theme.FONT_BOLD, 64)
        self.assertEqual(font.size, 64)

    def test_load_font_is_cached(self) -> None:
        self.assertIs(
            theme.load_font(theme.FONT_BOLD, 48),
            theme.load_font(theme.FONT_BOLD, 48),
        )

    def test_canvas_sizes(self) -> None:
        self.assertEqual(theme.FACEBOOK_SIZE, (1200, 630))
        self.assertEqual(theme.INSTAGRAM_SIZE, (1080, 1080))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_theme -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'cinema.social_cards.theme'`

- [ ] **Step 4: Write the implementation**

Create `cinema/social_cards/theme.py`:

```python
"""Visual constants for Fort Kent Cinema social cards.

Everything about how a card *looks* lives here, so the palette and type scale
can be retuned without touching layout or drawing code. Colours are sampled
from the YouTube thumbnail template (fkc-thumbnail-template-blank.png).
"""

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONTS_DIR = Path(__file__).resolve().parent / "fonts"
FONT_BOLD = str(FONTS_DIR / "Poppins-ExtraBold.ttf")
FONT_MEDIUM = str(FONTS_DIR / "Poppins-SemiBold.ttf")

# Palette
INK = (15, 19, 32)  # base field
INK_CENTRE = (27, 33, 54)  # brighter core of the radial background
INK_EDGE = (11, 14, 23)  # darkest corners
GOLD = (233, 192, 94)
CREAM = (253, 246, 224)
TREE = (5, 7, 12)

FACEBOOK_SIZE = (1200, 630)
INSTAGRAM_SIZE = (1080, 1080)

# Text glow: a tight cream halo over a wide gold bloom.
GLOW_TIGHT_RADIUS = 10
GLOW_WIDE_RADIUS = 34
GLOW_TIGHT_STRENGTH = 0.55
GLOW_WIDE_STRENGTH = 0.35


@lru_cache(maxsize=256)
def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font, memoised.

    Fitting a headline tries many sizes in a loop, so this gets called far more
    often than there are distinct fonts.
    """
    return ImageFont.truetype(path, size)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_theme -v 2`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add cinema/social_cards cinema/tests/test_social_cards_theme.py
git commit -m "feat(cinema): social card theme constants and vendored Poppins fonts"
```

---

### Task 2: CardData — the content rules

This is where nearly all the testable logic lives. **Do not import Pillow in this module.**

**Files:**
- Create: `cinema/social_cards/card.py`
- Test: `cinema/tests/test_social_cards_card.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `FACEBOOK: str`, `INSTAGRAM: str`, `PLATFORMS: tuple[str, ...]`
  - `BADGE_NOW_PLAYING: str`, `BADGE_COMING_SOON: str`
  - `BADGE_BY_PARAM: dict[str, str]`, `PARAM_BY_BADGE: dict[str, str]`, `BADGE_SLUGS: dict[str, str]`
  - `WORDMARK: str`, `FOOTER: str`
  - `Artwork(url: str, crop_bias: float)` — frozen dataclass
  - `default_badge(engagement: Engagement, today: date | None = None) -> str`
  - `format_date_line(start: date, end: date, badge: str) -> str`
  - `resolve_artwork(films: Sequence[Film], platform: str) -> tuple[Artwork, ...]`
  - `CardData` — frozen dataclass with fields `badge, headline, date_line, artwork, slug, wordmark, footer`
  - `CardData.from_engagement(engagement, platform, badge=None, today=None) -> CardData`

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_social_cards_card.py`:

```python
import datetime

from django.test import TestCase

from cinema.models import Engagement, EngagementFilm, Film, Screen
from cinema.social_cards import card as card_mod
from cinema.social_cards.card import (
    BADGE_COMING_SOON,
    BADGE_NOW_PLAYING,
    FACEBOOK,
    INSTAGRAM,
    Artwork,
    CardData,
    default_badge,
    format_date_line,
    resolve_artwork,
)

JULY_1 = datetime.date(2026, 7, 1)
JULY_7 = datetime.date(2026, 7, 7)


def make_film(title: str, **over: str) -> Film:
    defaults = {"poster_url": "", "backdrop_url": ""}
    defaults.update(over)
    return Film.objects.create(title=title, **defaults)


class DateLineTests(TestCase):
    def test_now_playing_multi_day(self) -> None:
        self.assertEqual(
            format_date_line(JULY_1, JULY_7, BADGE_NOW_PLAYING),
            "NOW THROUGH JULY 7",
        )

    def test_coming_soon_multi_day(self) -> None:
        self.assertEqual(
            format_date_line(JULY_1, JULY_7, BADGE_COMING_SOON),
            "STARTS JULY 1",
        )

    def test_single_day_is_the_same_for_both_badges(self) -> None:
        for badge in (BADGE_NOW_PLAYING, BADGE_COMING_SOON):
            self.assertEqual(
                format_date_line(JULY_1, JULY_1, badge),
                "ONE NIGHT ONLY · JULY 1",
            )

    def test_run_crossing_a_month_boundary(self) -> None:
        self.assertEqual(
            format_date_line(
                datetime.date(2026, 8, 29),
                datetime.date(2026, 9, 4),
                BADGE_NOW_PLAYING,
            ),
            "NOW THROUGH SEPTEMBER 4",
        )

    def test_no_year_is_shown(self) -> None:
        self.assertNotIn("2026", format_date_line(JULY_1, JULY_7, BADGE_NOW_PLAYING))


class BadgeDefaultTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)

    def _eng(self) -> Engagement:
        return Engagement.objects.create(
            screen=self.screen, start_date=JULY_1, end_date=JULY_7
        )

    def test_future_run_is_coming_soon(self) -> None:
        eng = self._eng()
        self.assertEqual(
            default_badge(eng, today=datetime.date(2026, 6, 30)), BADGE_COMING_SOON
        )

    def test_on_the_start_date_it_is_now_playing(self) -> None:
        eng = self._eng()
        self.assertEqual(default_badge(eng, today=JULY_1), BADGE_NOW_PLAYING)

    def test_mid_run_is_now_playing(self) -> None:
        eng = self._eng()
        self.assertEqual(
            default_badge(eng, today=datetime.date(2026, 7, 4)), BADGE_NOW_PLAYING
        )

    def test_past_run_is_now_playing(self) -> None:
        # Deliberate: the operator decides how to label a finished run.
        eng = self._eng()
        self.assertEqual(
            default_badge(eng, today=datetime.date(2026, 12, 1)), BADGE_NOW_PLAYING
        )


class ResolveArtworkTests(TestCase):
    def test_facebook_single_film_uses_poster_centred(self) -> None:
        film = make_film("Dune", poster_url="https://img/p.jpg",
                         backdrop_url="https://img/b.jpg")
        self.assertEqual(
            resolve_artwork([film], FACEBOOK),
            (Artwork("https://img/p.jpg", card_mod.CENTRE_CROP),),
        )

    def test_instagram_single_film_prefers_backdrop(self) -> None:
        film = make_film("Dune", poster_url="https://img/p.jpg",
                         backdrop_url="https://img/b.jpg")
        self.assertEqual(
            resolve_artwork([film], INSTAGRAM),
            (Artwork("https://img/b.jpg", card_mod.CENTRE_CROP),),
        )

    def test_instagram_falls_back_to_top_biased_poster(self) -> None:
        film = make_film("Dune", poster_url="https://img/p.jpg")
        self.assertEqual(
            resolve_artwork([film], INSTAGRAM),
            (Artwork("https://img/p.jpg", card_mod.TOP_CROP),),
        )

    def test_no_artwork_at_all(self) -> None:
        self.assertEqual(resolve_artwork([make_film("Dune")], INSTAGRAM), ())

    def test_no_films(self) -> None:
        self.assertEqual(resolve_artwork([], FACEBOOK), ())

    def test_two_films_split_into_two_posters(self) -> None:
        a = make_film("A", poster_url="https://img/a.jpg")
        b = make_film("B", poster_url="https://img/b.jpg")
        self.assertEqual(
            resolve_artwork([a, b], INSTAGRAM),
            (
                Artwork("https://img/a.jpg", card_mod.CENTRE_CROP),
                Artwork("https://img/b.jpg", card_mod.CENTRE_CROP),
            ),
        )

    def test_two_films_but_only_one_poster_falls_back_to_single(self) -> None:
        a = make_film("A", poster_url="https://img/a.jpg")
        b = make_film("B")
        self.assertEqual(
            resolve_artwork([a, b], FACEBOOK),
            (Artwork("https://img/a.jpg", card_mod.CENTRE_CROP),),
        )

    def test_three_films_use_the_first_two(self) -> None:
        films = [
            make_film(name, poster_url=f"https://img/{name}.jpg")
            for name in ("A", "B", "C")
        ]
        self.assertEqual(
            resolve_artwork(films, FACEBOOK),
            (
                Artwork("https://img/A.jpg", card_mod.CENTRE_CROP),
                Artwork("https://img/B.jpg", card_mod.CENTRE_CROP),
            ),
        )


class CardDataTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)

    def _eng(self, films: list[Film], **over: object) -> Engagement:
        defaults: dict[str, object] = {
            "screen": self.screen,
            "start_date": JULY_1,
            "end_date": JULY_7,
        }
        defaults.update(over)
        eng = Engagement.objects.create(**defaults)
        for i, film in enumerate(films, start=1):
            EngagementFilm.objects.create(engagement=eng, film=film, position=i)
        return eng

    def test_single_film_headline_and_slug(self) -> None:
        eng = self._eng([make_film("Dune", poster_url="https://img/p.jpg")])
        data = CardData.from_engagement(eng, FACEBOOK, today=JULY_1)
        self.assertEqual(data.headline, "DUNE")
        self.assertEqual(data.slug, "dune")
        self.assertEqual(data.badge, BADGE_NOW_PLAYING)
        self.assertEqual(data.date_line, "NOW THROUGH JULY 7")
        self.assertEqual(data.wordmark, "FORT KENT CINEMA")
        self.assertEqual(
            data.footer, "VISIT WWW.FORTKENTCINEMA.COM FOR SHOWTIMES"
        )

    def test_two_films_join_in_the_headline(self) -> None:
        eng = self._eng([make_film("Alien"), make_film("Aliens")])
        data = CardData.from_engagement(eng, FACEBOOK, today=JULY_1)
        self.assertEqual(data.headline, "ALIEN + ALIENS")

    def test_event_title_overrides_the_film_names(self) -> None:
        eng = self._eng(
            [make_film("Alien"), make_film("Aliens")],
            event_title="Xenomorph Double Feature",
        )
        data = CardData.from_engagement(eng, FACEBOOK, today=JULY_1)
        self.assertEqual(data.headline, "XENOMORPH DOUBLE FEATURE")
        self.assertEqual(data.slug, "xenomorph-double-feature")

    def test_engagement_with_no_films_falls_back(self) -> None:
        eng = self._eng([])
        data = CardData.from_engagement(eng, FACEBOOK, today=JULY_1)
        self.assertEqual(data.headline, "FORT KENT CINEMA")
        self.assertEqual(data.slug, f"engagement-{eng.pk}")
        self.assertEqual(data.artwork, ())

    def test_explicit_badge_overrides_the_date_derived_default(self) -> None:
        eng = self._eng([make_film("Dune")])
        data = CardData.from_engagement(
            eng, FACEBOOK, badge=BADGE_COMING_SOON,
            today=datetime.date(2026, 7, 4),
        )
        self.assertEqual(data.badge, BADGE_COMING_SOON)
        self.assertEqual(data.date_line, "STARTS JULY 1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_card -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'cinema.social_cards.card'`

- [ ] **Step 3: Write the implementation**

Create `cinema/social_cards/card.py`:

```python
"""Content rules for social cards.

Turns an Engagement into the exact strings and artwork URLs a card needs.
Deliberately free of Pillow: every rule here is testable without rendering a
pixel.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

from django.utils import timezone
from django.utils.text import slugify

from cinema.models import Engagement, Film

FACEBOOK = "facebook"
INSTAGRAM = "instagram"
PLATFORMS = (FACEBOOK, INSTAGRAM)

BADGE_NOW_PLAYING = "NOW PLAYING"
BADGE_COMING_SOON = "COMING SOON"

# Query-param spelling uses underscores; filename spelling uses hyphens.
BADGE_BY_PARAM = {
    "now_playing": BADGE_NOW_PLAYING,
    "coming_soon": BADGE_COMING_SOON,
}
PARAM_BY_BADGE = {badge: param for param, badge in BADGE_BY_PARAM.items()}
BADGE_SLUGS = {
    BADGE_NOW_PLAYING: "now-playing",
    BADGE_COMING_SOON: "coming-soon",
}

WORDMARK = "FORT KENT CINEMA"
FOOTER = "VISIT WWW.FORTKENTCINEMA.COM FOR SHOWTIMES"
FALLBACK_HEADLINE = "FORT KENT CINEMA"

# Vertical crop anchor: 0.0 keeps the top of the source, 0.5 the middle.
CENTRE_CROP = 0.5
TOP_CROP = 0.25


@dataclass(frozen=True)
class Artwork:
    """One image to place on the card, plus how to crop it."""

    url: str
    crop_bias: float


def _month_day(value: datetime.date) -> str:
    # Explicit day formatting rather than %-d, which is not portable.
    return f"{value:%B} {value.day}".upper()


def format_date_line(
    start: datetime.date, end: datetime.date, badge: str
) -> str:
    if start == end:
        return f"ONE NIGHT ONLY · {_month_day(start)}"
    if badge == BADGE_COMING_SOON:
        return f"STARTS {_month_day(start)}"
    return f"NOW THROUGH {_month_day(end)}"


def default_badge(
    engagement: Engagement, today: datetime.date | None = None
) -> str:
    """Coming Soon only for runs that have not started yet."""
    today = today or timezone.localdate()
    if engagement.start_date > today:
        return BADGE_COMING_SOON
    return BADGE_NOW_PLAYING


def _single_artwork(film: Film, platform: str) -> Artwork | None:
    """Best single image for one film on one platform.

    Instagram's artwork band is landscape, so a 16:9 backdrop is a far better
    fit than a 2:3 poster. When only a poster exists we crop toward its top —
    posters put key art up high and title treatments and credits at the bottom.
    """
    if platform == INSTAGRAM:
        if film.backdrop_url:
            return Artwork(film.backdrop_url, CENTRE_CROP)
        if film.poster_url:
            return Artwork(film.poster_url, TOP_CROP)
        return None
    if film.poster_url:
        return Artwork(film.poster_url, CENTRE_CROP)
    return None


def resolve_artwork(
    films: Sequence[Film], platform: str
) -> tuple[Artwork, ...]:
    """Zero, one, or two images.

    Two only when the first two films both have posters — a split panel with
    one half empty looks like a bug, so a partial pair falls back to single.
    """
    if len(films) >= 2:
        posters = [film.poster_url for film in films[:2] if film.poster_url]
        if len(posters) == 2:
            return tuple(Artwork(url, CENTRE_CROP) for url in posters)
    for film in films:
        art = _single_artwork(film, platform)
        if art is not None:
            return (art,)
    return ()


@dataclass(frozen=True)
class CardData:
    badge: str
    headline: str
    date_line: str
    artwork: tuple[Artwork, ...]
    slug: str
    wordmark: str = WORDMARK
    footer: str = FOOTER

    @classmethod
    def from_engagement(
        cls,
        engagement: Engagement,
        platform: str,
        badge: str | None = None,
        today: datetime.date | None = None,
    ) -> CardData:
        badge = badge or default_badge(engagement, today)
        title = engagement.display_title.strip()
        return cls(
            badge=badge,
            headline=(title or FALLBACK_HEADLINE).upper(),
            date_line=format_date_line(
                engagement.start_date, engagement.end_date, badge
            ),
            artwork=resolve_artwork(engagement.ordered_films, platform),
            slug=slugify(title) or f"engagement-{engagement.pk}",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_card -v 2`
Expected: PASS (21 tests)

- [ ] **Step 5: Lint**

```bash
.venv/bin/python -m flake8 cinema/social_cards cinema/tests/test_social_cards_card.py
```
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add cinema/social_cards/card.py cinema/tests/test_social_cards_card.py
git commit -m "feat(cinema): CardData content rules for social cards"
```

---

### Task 3: Artwork fetching

**Files:**
- Create: `cinema/social_cards/posters.py`
- Test: `cinema/tests/test_social_cards_posters.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `upsize_tmdb_url(url: str) -> str`
  - `fetch_artwork(url: str) -> Image.Image | None`
  - `MAX_BYTES: int`, `MAX_PIXELS_PER_AXIS: int`, `CACHE_TTL_SECONDS: int`, `TIMEOUT_SECONDS: int`

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_social_cards_posters.py`:

```python
from io import BytesIO
from unittest import mock

import requests
from django.core.cache import cache
from django.test import TestCase
from PIL import Image

from cinema.social_cards import posters


def png_bytes(width: int = 40, height: int = 60) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200) -> None:
        self.content = content
        self.status_code = status
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class UpsizeTests(TestCase):
    def test_w500_becomes_original(self) -> None:
        self.assertEqual(
            posters.upsize_tmdb_url(
                "https://image.tmdb.org/t/p/w500/abc.jpg"
            ),
            "https://image.tmdb.org/t/p/original/abc.jpg",
        )

    def test_already_original_is_unchanged(self) -> None:
        url = "https://image.tmdb.org/t/p/original/abc.jpg"
        self.assertEqual(posters.upsize_tmdb_url(url), url)

    def test_non_tmdb_url_passes_through(self) -> None:
        url = "https://example.com/images/w500/abc.jpg"
        self.assertEqual(posters.upsize_tmdb_url(url), url)

    def test_empty_string(self) -> None:
        self.assertEqual(posters.upsize_tmdb_url(""), "")


class FetchArtworkTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_empty_url_returns_none_without_a_request(self) -> None:
        with mock.patch.object(posters.requests, "get") as get:
            self.assertIsNone(posters.fetch_artwork(""))
        get.assert_not_called()

    def test_successful_fetch_returns_rgb_image(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(png_bytes())
        ):
            image = posters.fetch_artwork("https://img/a.png")
        assert image is not None
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (40, 60))

    def test_fetch_upsizes_tmdb_urls(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(png_bytes())
        ) as get:
            posters.fetch_artwork("https://image.tmdb.org/t/p/w500/a.png")
        self.assertEqual(
            get.call_args.args[0], "https://image.tmdb.org/t/p/original/a.png"
        )

    def test_second_fetch_is_served_from_cache(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(png_bytes())
        ) as get:
            posters.fetch_artwork("https://img/a.png")
            posters.fetch_artwork("https://img/a.png")
        self.assertEqual(get.call_count, 1)

    def test_timeout_returns_none(self) -> None:
        with mock.patch.object(
            posters.requests, "get", side_effect=requests.Timeout("slow")
        ):
            self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_http_error_returns_none(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(b"nope", 404)
        ):
            self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_oversize_response_returns_none(self) -> None:
        big = b"x" * (posters.MAX_BYTES + 1)
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(big)
        ):
            self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_undecodable_body_returns_none(self) -> None:
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(b"not an image")
        ):
            self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_absurdly_large_image_returns_none(self) -> None:
        oversized = png_bytes()
        with mock.patch.object(
            posters.requests, "get", return_value=FakeResponse(oversized)
        ):
            with mock.patch.object(
                posters.Image, "open"
            ) as opener:
                opener.return_value.size = (
                    posters.MAX_PIXELS_PER_AXIS + 1,
                    10,
                )
                self.assertIsNone(posters.fetch_artwork("https://img/a.png"))

    def test_failed_fetch_is_not_cached(self) -> None:
        with mock.patch.object(
            posters.requests, "get", side_effect=requests.Timeout("slow")
        ) as get:
            posters.fetch_artwork("https://img/a.png")
            posters.fetch_artwork("https://img/a.png")
        self.assertEqual(get.call_count, 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_posters -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'cinema.social_cards.posters'`

- [ ] **Step 3: Write the implementation**

Create `cinema/social_cards/posters.py`:

```python
"""Fetching artwork for social cards.

Artwork is never load-bearing: every failure path returns None and the layout
falls back to an empty framed panel.
"""

from __future__ import annotations

import hashlib
import logging
import re
from io import BytesIO

import requests
from django.core.cache import cache
from PIL import Image

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 8
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS_PER_AXIS = 8000
CACHE_TTL_SECONDS = 60 * 60 * 24
CACHE_PREFIX = "social-card-art:"

_TMDB_SIZE_RE = re.compile(
    r"(https?://image\.tmdb\.org/t/p/)(w\d+|h\d+|original)(/)"
)


def upsize_tmdb_url(url: str) -> str:
    """Ask TMDB for the full-resolution file.

    Film.poster_url stores w500 URLs, which upscale badly onto a 1080px canvas.
    Non-TMDB URLs pass through untouched.
    """
    return _TMDB_SIZE_RE.sub(r"\1original\3", url, count=1)


def _download(url: str) -> bytes | None:
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("social card artwork fetch failed: %s", url)
        return None
    content = response.content
    if len(content) > MAX_BYTES:
        logger.warning(
            "social card artwork too large (%d bytes): %s", len(content), url
        )
        return None
    return content


def _decode(data: bytes) -> Image.Image | None:
    try:
        image = Image.open(BytesIO(data))
        width, height = image.size
        if max(width, height) > MAX_PIXELS_PER_AXIS:
            logger.warning("social card artwork too many pixels: %dx%d",
                           width, height)
            return None
        return image.convert("RGB")
    except Exception:
        logger.warning("social card artwork could not be decoded")
        return None


def fetch_artwork(url: str) -> Image.Image | None:
    """Return a decoded RGB image for `url`, or None on any failure."""
    if not url:
        return None
    target = upsize_tmdb_url(url)
    key = CACHE_PREFIX + hashlib.sha256(target.encode()).hexdigest()
    data = cache.get(key)
    if data is None:
        data = _download(target)
        if data is None:
            return None
        cache.set(key, data, CACHE_TTL_SECONDS)
    return _decode(data)
```

The broad `except Exception` in `_decode` is deliberate: Pillow raises a wide and version-dependent family of exceptions on malformed input, and the only sensible response to any of them is the same fallback.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_posters -v 2`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add cinema/social_cards/posters.py cinema/tests/test_social_cards_posters.py
git commit -m "feat(cinema): artwork fetching with cache and size guards"
```

---

### Task 4: Text fitting and glowing text

**Files:**
- Create: `cinema/social_cards/draw.py`
- Test: `cinema/tests/test_social_cards_draw.py`

**Interfaces:**
- Consumes: `theme.load_font`, `theme.GOLD`, `theme.CREAM`, glow constants.
- Produces:
  - `wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]`
  - `fit_text(text, font_path, box_width, box_height, max_size, min_size, step=4, line_spacing=0.98) -> tuple[list[str], ImageFont.FreeTypeFont]`
  - `line_height(font: ImageFont.FreeTypeFont, line_spacing: float) -> int`
  - `draw_glow_text(base, lines, font, origin, line_spacing, body_color, accent_color) -> int` — returns the y coordinate just below the last line
  - `draw_plain_text(base, text, font, origin, color) -> int`

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_social_cards_draw.py`:

```python
from django.test import TestCase
from PIL import Image

from cinema.social_cards import draw, theme


class WrapTests(TestCase):
    def setUp(self) -> None:
        self.font = theme.load_font(theme.FONT_BOLD, 40)

    def test_empty_text_wraps_to_nothing(self) -> None:
        self.assertEqual(draw.wrap_lines("", self.font, 500), [])

    def test_short_text_stays_on_one_line(self) -> None:
        self.assertEqual(draw.wrap_lines("DUNE", self.font, 500), ["DUNE"])

    def test_long_text_wraps(self) -> None:
        lines = draw.wrap_lines(
            "THE SUPER MARIO GALAXY MOVIE", self.font, 400
        )
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(self.font.getlength(line), 400)

    def test_a_single_unbreakable_word_is_kept_whole(self) -> None:
        self.assertEqual(
            draw.wrap_lines("SUPERCALIFRAGILISTIC", self.font, 50),
            ["SUPERCALIFRAGILISTIC"],
        )


class FitTextTests(TestCase):
    def test_short_headline_uses_the_maximum_size(self) -> None:
        lines, font = draw.fit_text(
            "DUNE", theme.FONT_BOLD, 640, 250, max_size=92, min_size=44
        )
        self.assertEqual(lines, ["DUNE"])
        self.assertEqual(font.size, 92)

    def test_long_headline_shrinks(self) -> None:
        _, font = draw.fit_text(
            "THE LORD OF THE RINGS THE RETURN OF THE KING EXTENDED EDITION",
            theme.FONT_BOLD,
            640,
            250,
            max_size=92,
            min_size=44,
        )
        self.assertLess(font.size, 92)

    def test_it_never_shrinks_below_the_floor(self) -> None:
        _, font = draw.fit_text(
            " ".join(["VERYLONGWORD"] * 40),
            theme.FONT_BOLD,
            640,
            250,
            max_size=92,
            min_size=44,
        )
        self.assertEqual(font.size, 44)

    def test_fitted_block_fits_the_box(self) -> None:
        lines, font = draw.fit_text(
            "THE SUPER MARIO GALAXY MOVIE",
            theme.FONT_BOLD,
            640,
            250,
            max_size=92,
            min_size=44,
        )
        height = len(lines) * draw.line_height(font, 0.98)
        self.assertLessEqual(height, 250)
        for line in lines:
            self.assertLessEqual(font.getlength(line), 640)


class GlowTextTests(TestCase):
    def _canvas(self) -> Image.Image:
        return Image.new("RGBA", (600, 300), theme.INK + (255,))

    def test_it_draws_something(self) -> None:
        canvas = self._canvas()
        before = canvas.tobytes()
        font = theme.load_font(theme.FONT_BOLD, 48)
        draw.draw_glow_text(
            canvas, ["DUNE"], font, (20, 20), 0.98, theme.CREAM, theme.GOLD
        )
        self.assertNotEqual(canvas.tobytes(), before)

    def test_it_returns_the_baseline_below_the_block(self) -> None:
        canvas = self._canvas()
        font = theme.load_font(theme.FONT_BOLD, 48)
        bottom = draw.draw_glow_text(
            canvas, ["ONE", "TWO"], font, (20, 20), 0.98,
            theme.CREAM, theme.GOLD,
        )
        self.assertEqual(bottom, 20 + 2 * draw.line_height(font, 0.98))

    def test_last_line_is_gold_when_the_headline_wraps(self) -> None:
        canvas = self._canvas()
        font = theme.load_font(theme.FONT_BOLD, 60)
        draw.draw_glow_text(
            canvas, ["AAAA", "BBBB"], font, (20, 20), 0.98,
            theme.CREAM, theme.GOLD,
        )
        colors = {c for _, c in canvas.convert("RGB").getcolors(maxcolors=1 << 20)}
        self.assertIn(theme.GOLD, colors)
        self.assertIn(theme.CREAM, colors)

    def test_single_line_headline_has_no_gold_glyphs(self) -> None:
        canvas = self._canvas()
        font = theme.load_font(theme.FONT_BOLD, 60)
        draw.draw_glow_text(
            canvas, ["AAAA"], font, (20, 20), 0.98, theme.CREAM, theme.GOLD
        )
        colors = {c for _, c in canvas.convert("RGB").getcolors(maxcolors=1 << 20)}
        self.assertIn(theme.CREAM, colors)
        self.assertNotIn(theme.GOLD, colors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_draw -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'cinema.social_cards.draw'`

- [ ] **Step 3: Write the implementation**

Create `cinema/social_cards/draw.py`:

```python
"""Drawing primitives for social cards.

Knows about pixels and the Fort Kent Cinema look. Knows nothing about
engagements — everything here takes plain strings, boxes, and colours.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import theme

RGB = tuple[int, int, int]
Box = tuple[int, int, int, int]


def line_height(font: ImageFont.FreeTypeFont, line_spacing: float) -> int:
    return int(font.size * line_spacing)


def wrap_lines(
    text: str, font: ImageFont.FreeTypeFont, max_width: float
) -> list[str]:
    """Greedy word wrap. A single word wider than the box is kept whole."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def fit_text(
    text: str,
    font_path: str,
    box_width: int,
    box_height: int,
    max_size: int,
    min_size: int,
    step: int = 4,
    line_spacing: float = 0.98,
) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """Largest size at which `text` wraps into the box.

    If it still does not fit at `min_size` we render at `min_size` anyway and
    allow the overflow — a title that long is a signal to set a shorter
    event_title, not a reason to render something illegible.
    """
    size = max_size
    while size > min_size:
        font = theme.load_font(font_path, size)
        lines = wrap_lines(text, font, box_width)
        widest = max((font.getlength(line) for line in lines), default=0.0)
        height = len(lines) * line_height(font, line_spacing)
        if height <= box_height and widest <= box_width:
            return lines, font
        size -= step
    font = theme.load_font(font_path, min_size)
    return wrap_lines(text, font, box_width), font


def _tint(layer: Image.Image, color: RGB, strength: float) -> Image.Image:
    """Recolour a blurred alpha mask, scaling its opacity."""
    alpha = layer.getchannel("A").point(lambda v: int(v * strength))
    tinted = Image.new("RGBA", layer.size, color + (0,))
    tinted.putalpha(alpha)
    return tinted


def draw_glow_text(
    base: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    origin: tuple[int, int],
    line_spacing: float,
    body_color: RGB,
    accent_color: RGB,
) -> int:
    """Draw glowing text; return the y coordinate just below the last line.

    When the block wraps to two or more lines the final line takes
    `accent_color`, matching the template's cream-headline-with-gold-last-line
    treatment. A single line is drawn entirely in `body_color`.
    """
    x, y = origin
    step = line_height(font, line_spacing)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    for index, line in enumerate(lines):
        is_last = index == len(lines) - 1
        color = accent_color if (len(lines) > 1 and is_last) else body_color
        pen.text((x, y + index * step), line, font=font, fill=color + (255,))

    wide = _tint(
        layer.filter(ImageFilter.GaussianBlur(theme.GLOW_WIDE_RADIUS)),
        theme.GOLD,
        theme.GLOW_WIDE_STRENGTH,
    )
    tight = _tint(
        layer.filter(ImageFilter.GaussianBlur(theme.GLOW_TIGHT_RADIUS)),
        theme.CREAM,
        theme.GLOW_TIGHT_STRENGTH,
    )
    base.alpha_composite(wide)
    base.alpha_composite(tight)
    base.alpha_composite(layer)
    return y + len(lines) * step


def draw_plain_text(
    base: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    origin: tuple[int, int],
    color: RGB,
) -> int:
    """Crisp, unglowed text. Returns the y coordinate below it."""
    pen = ImageDraw.Draw(base)
    pen.text(origin, text, font=font, fill=color + (255,))
    return origin[1] + line_height(font, 1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_draw -v 2`
Expected: PASS (12 tests)

If `test_last_line_is_gold_when_the_headline_wraps` fails because no pixel is exactly `theme.GOLD`, the glow compositing is bleeding into the glyph cores. The crisp layer is composited last and must be fully opaque — check that `fill=color + (255,)` is in place.

- [ ] **Step 5: Commit**

```bash
git add cinema/social_cards/draw.py cinema/tests/test_social_cards_draw.py
git commit -m "feat(cinema): text fitting and glowing text primitives"
```

---

### Task 5: Background, ornaments, and artwork placement

**Files:**
- Modify: `cinema/social_cards/draw.py` (append)
- Modify: `cinema/tests/test_social_cards_draw.py` (append)

**Interfaces:**
- Consumes: `theme` constants, `Box = tuple[int, int, int, int]` from Task 4.
- Produces:
  - `make_background(size: tuple[int, int]) -> Image.Image` — RGBA
  - `draw_trees(base: Image.Image, band_height: int) -> None`
  - `draw_bulbs(base, start, end, count, radius) -> None`
  - `cover_crop(image, target_width, target_height, crop_bias) -> Image.Image`
  - `place_artwork(base, image, box, crop_bias) -> None`
  - `fade_edge(base, box, direction, color) -> None` — `direction` is `"left"` or `"bottom"`
  - `draw_dashed_frame(base, box, color, dash=18, gap=14, width=3) -> None`
  - `draw_outlined_badge(base, text, font, origin, color, padding=(24, 12), border=3) -> None`

- [ ] **Step 1: Write the failing test**

Append to `cinema/tests/test_social_cards_draw.py`:

```python
class BackgroundTests(TestCase):
    def test_size_and_mode(self) -> None:
        bg = draw.make_background((300, 200))
        self.assertEqual(bg.size, (300, 200))
        self.assertEqual(bg.mode, "RGBA")

    def test_it_is_a_gradient_not_a_flat_fill(self) -> None:
        bg = draw.make_background((300, 200)).convert("RGB")
        self.assertGreater(len(bg.getcolors(maxcolors=1 << 20) or []), 1)

    def test_it_is_brighter_toward_the_upper_left(self) -> None:
        bg = draw.make_background((300, 200)).convert("RGB")
        self.assertGreater(sum(bg.getpixel((50, 60))), sum(bg.getpixel((290, 195))))


class OrnamentTests(TestCase):
    def _canvas(self) -> Image.Image:
        return Image.new("RGBA", (400, 300), theme.INK + (255,))

    def test_trees_darken_the_bottom_band(self) -> None:
        canvas = self._canvas()
        draw.draw_trees(canvas, band_height=60)
        self.assertLess(
            sum(canvas.convert("RGB").getpixel((0, 299))), sum(theme.INK)
        )

    def test_trees_leave_the_top_alone(self) -> None:
        canvas = self._canvas()
        draw.draw_trees(canvas, band_height=60)
        self.assertEqual(canvas.convert("RGB").getpixel((200, 10)), theme.INK)

    def test_trees_are_deterministic(self) -> None:
        first, second = self._canvas(), self._canvas()
        draw.draw_trees(first, band_height=60)
        draw.draw_trees(second, band_height=60)
        self.assertEqual(first.tobytes(), second.tobytes())

    def test_bulbs_add_gold(self) -> None:
        canvas = self._canvas()
        draw.draw_bulbs(canvas, (200, 20), (200, 280), count=6, radius=6)
        pixels = canvas.convert("RGB").getdata()
        self.assertTrue(any(r > 180 and g > 140 and b < 140 for r, g, b in pixels))

    def test_bulbs_work_horizontally_too(self) -> None:
        canvas = self._canvas()
        before = canvas.tobytes()
        draw.draw_bulbs(canvas, (20, 150), (380, 150), count=6, radius=6)
        self.assertNotEqual(canvas.tobytes(), before)


class CoverCropTests(TestCase):
    def test_output_is_exactly_the_target_size(self) -> None:
        source = Image.new("RGB", (400, 600), (10, 20, 30))
        result = draw.cover_crop(source, 300, 200, 0.5)
        self.assertEqual(result.size, (300, 200))

    def test_top_bias_keeps_the_top_of_the_source(self) -> None:
        source = Image.new("RGB", (100, 400), (0, 0, 0))
        for y in range(200):
            for x in range(100):
                source.putpixel((x, y), (255, 255, 255))
        top_biased = draw.cover_crop(source, 100, 50, 0.0)
        centred = draw.cover_crop(source, 100, 50, 0.5)
        self.assertGreater(
            sum(sum(p) for p in top_biased.getdata()),
            sum(sum(p) for p in centred.getdata()),
        )

    def test_it_upscales_a_small_source(self) -> None:
        source = Image.new("RGB", (50, 50), (10, 20, 30))
        self.assertEqual(draw.cover_crop(source, 400, 300, 0.5).size, (400, 300))


class PanelTests(TestCase):
    def _canvas(self) -> Image.Image:
        return Image.new("RGBA", (400, 300), theme.INK + (255,))

    def test_place_artwork_fills_the_box(self) -> None:
        canvas = self._canvas()
        art = Image.new("RGB", (100, 150), (250, 10, 10))
        draw.place_artwork(canvas, art, (200, 0, 400, 300), 0.5)
        self.assertEqual(canvas.convert("RGB").getpixel((300, 150)), (250, 10, 10))
        self.assertEqual(canvas.convert("RGB").getpixel((10, 150)), theme.INK)

    def test_fade_edge_left_darkens_the_left_of_the_box(self) -> None:
        canvas = self._canvas()
        art = Image.new("RGB", (100, 150), (250, 250, 250))
        draw.place_artwork(canvas, art, (200, 0, 400, 300), 0.5)
        draw.fade_edge(canvas, (200, 0, 400, 300), "left", theme.INK)
        rgb = canvas.convert("RGB")
        self.assertLess(sum(rgb.getpixel((202, 150))), sum(rgb.getpixel((395, 150))))

    def test_fade_edge_bottom_darkens_the_bottom_of_the_box(self) -> None:
        canvas = self._canvas()
        art = Image.new("RGB", (100, 150), (250, 250, 250))
        draw.place_artwork(canvas, art, (0, 0, 400, 200), 0.5)
        draw.fade_edge(canvas, (0, 0, 400, 200), "bottom", theme.INK)
        rgb = canvas.convert("RGB")
        self.assertLess(sum(rgb.getpixel((200, 198))), sum(rgb.getpixel((200, 5))))

    def test_dashed_frame_draws_gold(self) -> None:
        canvas = self._canvas()
        before = canvas.tobytes()
        draw.draw_dashed_frame(canvas, (20, 20, 380, 280), theme.GOLD)
        self.assertNotEqual(canvas.tobytes(), before)

    def test_outlined_badge_draws_text_and_border(self) -> None:
        canvas = self._canvas()
        font = theme.load_font(theme.FONT_MEDIUM, 20)
        draw.draw_outlined_badge(
            canvas, "NOW PLAYING", font, (20, 20), theme.GOLD
        )
        colors = {c for _, c in canvas.convert("RGB").getcolors(maxcolors=1 << 20)}
        self.assertIn(theme.GOLD, colors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_draw -v 2`
Expected: FAIL — `AttributeError: module 'cinema.social_cards.draw' has no attribute 'make_background'`

- [ ] **Step 3: Write the implementation**

Append to `cinema/social_cards/draw.py`:

```python
import math

# Fixed peak heights, cycled across the tree line. A literal rather than
# random() so a given card always renders byte-identically.
_TREE_PEAKS = (0.60, 0.95, 0.45, 0.80, 0.35, 0.70, 0.50, 0.90, 0.40, 0.75)
_TREE_SPACING = 30


def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def make_background(size: tuple[int, int]) -> Image.Image:
    """Radial navy field, brighter toward the upper left.

    Rendered tiny and upscaled: a 64x64 gradient resized with LANCZOS is
    smooth, and skips a million per-pixel Python calls.
    """
    small = Image.new("RGB", (64, 64))
    pixels = small.load()
    assert pixels is not None
    centre_x, centre_y = 0.18, 0.30
    for y in range(64):
        for x in range(64):
            dx = (x / 63) - centre_x
            dy = (y / 63) - centre_y
            distance = math.hypot(dx * 1.1, dy * 1.4)
            pixels[x, y] = _lerp(
                theme.INK_CENTRE, theme.INK_EDGE, min(1.0, distance / 0.95)
            )
    return small.resize(size, Image.Resampling.LANCZOS).convert("RGBA")


def draw_trees(base: Image.Image, band_height: int) -> None:
    """Pine silhouette along the bottom edge."""
    width, height = base.size
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    for index, x in enumerate(range(-_TREE_SPACING, width + _TREE_SPACING,
                                    _TREE_SPACING)):
        peak = _TREE_PEAKS[index % len(_TREE_PEAKS)]
        apex_y = height - int(band_height * peak)
        half = _TREE_SPACING
        pen.polygon(
            [(x - half, height), (x, apex_y), (x + half, height)],
            fill=theme.TREE + (215,),
        )
    base.alpha_composite(layer)


def draw_bulbs(
    base: Image.Image,
    start: tuple[int, int],
    end: tuple[int, int],
    count: int,
    radius: int,
) -> None:
    """A marquee bulb strip: evenly spaced glowing gold dots from start to end.

    Works for any straight line, so the same call draws Facebook's vertical
    seam and Instagram's horizontal one.
    """
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    steps = max(count - 1, 1)
    for index in range(count):
        t = index / steps
        cx = round(start[0] + (end[0] - start[0]) * t)
        cy = round(start[1] + (end[1] - start[1]) * t)
        pen.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=theme.GOLD + (255,),
        )
    glow = _tint(
        layer.filter(ImageFilter.GaussianBlur(radius * 2)), theme.GOLD, 0.85
    )
    base.alpha_composite(glow)
    base.alpha_composite(layer)


def cover_crop(
    image: Image.Image, target_width: int, target_height: int, crop_bias: float
) -> Image.Image:
    """Scale to cover the target box, then crop.

    `crop_bias` picks the vertical anchor: 0.0 keeps the top of the source,
    0.5 the middle, 1.0 the bottom. Horizontal crop is always centred.
    """
    source_width, source_height = image.size
    scale = max(target_width / source_width, target_height / source_height)
    scaled = image.resize(
        (max(round(source_width * scale), target_width),
         max(round(source_height * scale), target_height)),
        Image.Resampling.LANCZOS,
    )
    scaled_width, scaled_height = scaled.size
    left = round((scaled_width - target_width) / 2)
    top = round((scaled_height - target_height) * crop_bias)
    return scaled.crop(
        (left, top, left + target_width, top + target_height)
    )


def place_artwork(
    base: Image.Image, image: Image.Image, box: Box, crop_bias: float
) -> None:
    left, top, right, bottom = box
    cropped = cover_crop(image, right - left, bottom - top, crop_bias)
    base.paste(cropped.convert("RGBA"), (left, top))


def fade_edge(
    base: Image.Image, box: Box, direction: str, color: RGB
) -> None:
    """Fade `box` into `color` from one edge.

    "left" fades in from the left edge (Facebook, where artwork meets type);
    "bottom" fades out at the bottom (Instagram, where the band meets the
    solid text area).
    """
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    if direction == "left":
        ramp = Image.linear_gradient("L").rotate(270, expand=True)
        ramp = ramp.resize((width, height), Image.Resampling.BILINEAR)
    elif direction == "bottom":
        ramp = Image.linear_gradient("L").resize(
            (width, height), Image.Resampling.BILINEAR
        )
    else:
        raise ValueError(f"unknown fade direction: {direction}")
    overlay = Image.new("RGBA", (width, height), color + (0,))
    overlay.putalpha(ramp)
    base.alpha_composite(overlay, (left, top))


def draw_dashed_frame(
    base: Image.Image,
    box: Box,
    color: RGB,
    dash: int = 18,
    gap: int = 14,
    width: int = 3,
) -> None:
    """The template's empty-artwork state."""
    left, top, right, bottom = box
    pen = ImageDraw.Draw(base)
    stroke = color + (255,)
    for x in range(left, right, dash + gap):
        end_x = min(x + dash, right)
        pen.line([(x, top), (end_x, top)], fill=stroke, width=width)
        pen.line([(x, bottom), (end_x, bottom)], fill=stroke, width=width)
    for y in range(top, bottom, dash + gap):
        end_y = min(y + dash, bottom)
        pen.line([(left, y), (left, end_y)], fill=stroke, width=width)
        pen.line([(right, y), (right, end_y)], fill=stroke, width=width)


def draw_outlined_badge(
    base: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    origin: tuple[int, int],
    color: RGB,
    padding: tuple[int, int] = (24, 12),
    border: int = 3,
) -> None:
    """The template's CATEGORY box: text in a thin outlined rectangle."""
    x, y = origin
    pad_x, pad_y = padding
    text_width = font.getlength(text)
    text_height = font.size
    pen = ImageDraw.Draw(base)
    pen.rectangle(
        [x, y, x + round(text_width) + pad_x * 2, y + text_height + pad_y * 2],
        outline=color + (255,),
        width=border,
    )
    pen.text((x + pad_x, y + pad_y), text, font=font, fill=color + (255,))
```

Move the `import math` to the top of the file alongside the other imports before committing — it is shown here only to keep the appended block self-contained.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_draw -v 2`
Expected: PASS (28 tests)

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m flake8 cinema/social_cards cinema/tests/test_social_cards_draw.py
git add cinema/social_cards/draw.py cinema/tests/test_social_cards_draw.py
git commit -m "feat(cinema): background, marquee, tree, and artwork primitives"
```

---

### Task 6: Layouts and the public entry point

**Files:**
- Create: `cinema/social_cards/layouts.py`
- Modify: `cinema/social_cards/__init__.py`
- Test: `cinema/tests/test_social_cards_layouts.py`

**Interfaces:**
- Consumes: `theme`, `card` (`CardData`, `Artwork`, `FACEBOOK`, `INSTAGRAM`, `BADGE_SLUGS`), `posters.fetch_artwork`, all of `draw`.
- Produces:
  - `layouts.render(card_data: CardData, platform: str, images: Sequence[tuple[Image.Image, float]]) -> bytes`
  - `social_cards.render_card(engagement, platform, badge=None, today=None) -> tuple[bytes, str]` — returns `(png_bytes, filename)`
  - `social_cards.card_filename(card_data: CardData, platform: str) -> str`

`render_card` returns the filename alongside the bytes so callers never rebuild
`CardData` just to name the download.

`render()` takes already-fetched images so that layout code never touches the
network and is trivially testable. Each entry pairs an image with its crop bias.

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_social_cards_layouts.py`:

```python
import datetime
from io import BytesIO
from unittest import mock

from django.test import TestCase
from PIL import Image

from cinema.models import Engagement, EngagementFilm, Film, Screen
from cinema.social_cards import card_filename, render_card
from cinema.social_cards import layouts
from cinema.social_cards.card import (
    BADGE_COMING_SOON,
    BADGE_NOW_PLAYING,
    FACEBOOK,
    INSTAGRAM,
    CardData,
)

JULY_1 = datetime.date(2026, 7, 1)
JULY_7 = datetime.date(2026, 7, 7)


def a_card(**over: object) -> CardData:
    defaults: dict[str, object] = {
        "badge": BADGE_NOW_PLAYING,
        "headline": "THE SUPER MARIO GALAXY MOVIE",
        "date_line": "NOW THROUGH JULY 7",
        "artwork": (),
        "slug": "the-super-mario-galaxy-movie",
    }
    defaults.update(over)
    return CardData(**defaults)  # type: ignore[arg-type]


def an_image(color: tuple[int, int, int] = (200, 40, 40)) -> Image.Image:
    return Image.new("RGB", (400, 600), color)


def open_png(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


class RenderTests(TestCase):
    def test_facebook_dimensions(self) -> None:
        png = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        self.assertEqual(open_png(png).size, (1200, 630))

    def test_instagram_dimensions(self) -> None:
        png = layouts.render(a_card(), INSTAGRAM, [(an_image(), 0.5)])
        self.assertEqual(open_png(png).size, (1080, 1080))

    def test_output_is_a_png(self) -> None:
        png = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        self.assertEqual(open_png(png).format, "PNG")

    def test_the_canvas_is_actually_drawn_on(self) -> None:
        png = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        colors = open_png(png).convert("RGB").getcolors(maxcolors=1 << 22)
        assert colors is not None
        self.assertGreater(len(colors), 500)

    def test_renders_without_artwork(self) -> None:
        png = layouts.render(a_card(), INSTAGRAM, [])
        self.assertEqual(open_png(png).size, (1080, 1080))

    def test_renders_a_two_panel_split(self) -> None:
        png = layouts.render(
            a_card(), INSTAGRAM,
            [(an_image((250, 10, 10)), 0.5), (an_image((10, 10, 250)), 0.5)],
        )
        image = open_png(png).convert("RGB")
        left = image.getpixel((270, 300))
        right = image.getpixel((810, 300))
        self.assertNotEqual(left, right)

    def test_a_very_long_headline_still_renders(self) -> None:
        png = layouts.render(
            a_card(headline="A" * 120), FACEBOOK, [(an_image(), 0.5)]
        )
        self.assertEqual(open_png(png).size, (1200, 630))

    def test_unknown_platform_raises(self) -> None:
        with self.assertRaises(ValueError):
            layouts.render(a_card(), "tiktok", [])

    def test_rendering_is_deterministic(self) -> None:
        first = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        second = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        self.assertEqual(first, second)


class EntryPointTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(
            title="Dune", poster_url="https://image.tmdb.org/t/p/w500/d.jpg"
        )
        self.eng = Engagement.objects.create(
            screen=self.screen, start_date=JULY_1, end_date=JULY_7
        )
        EngagementFilm.objects.create(
            engagement=self.eng, film=self.film, position=1
        )

    def test_render_card_fetches_and_renders(self) -> None:
        with mock.patch(
            "cinema.social_cards.fetch_artwork", return_value=an_image()
        ) as fetch:
            png, filename = render_card(self.eng, FACEBOOK, today=JULY_1)
        fetch.assert_called_once_with("https://image.tmdb.org/t/p/w500/d.jpg")
        self.assertEqual(open_png(png).size, (1200, 630))
        self.assertEqual(filename, "fkc-dune-now-playing-facebook.png")

    def test_render_card_survives_a_failed_fetch(self) -> None:
        with mock.patch("cinema.social_cards.fetch_artwork", return_value=None):
            png, _ = render_card(self.eng, INSTAGRAM, today=JULY_1)
        self.assertEqual(open_png(png).size, (1080, 1080))

    def test_filename_uses_hyphenated_badge(self) -> None:
        data = CardData.from_engagement(self.eng, FACEBOOK, today=JULY_1)
        self.assertEqual(
            card_filename(data, FACEBOOK), "fkc-dune-now-playing-facebook.png"
        )

    def test_filename_for_coming_soon_instagram(self) -> None:
        data = CardData.from_engagement(
            self.eng, INSTAGRAM, badge=BADGE_COMING_SOON, today=JULY_1
        )
        self.assertEqual(
            card_filename(data, INSTAGRAM),
            "fkc-dune-coming-soon-instagram.png",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_layouts -v 2`
Expected: FAIL — `ImportError: cannot import name 'card_filename' from 'cinema.social_cards'`

- [ ] **Step 3: Write the layouts implementation**

Create `cinema/social_cards/layouts.py`:

```python
"""Canvas geometry for social cards.

The only module that knows where things sit. Takes already-fetched artwork so
it never touches the network.
"""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

from PIL import Image

from . import draw, theme
from .card import FACEBOOK, INSTAGRAM, CardData

ArtworkImages = Sequence[tuple[Image.Image, float]]

PANEL_GAP = 8
FOOTER_STRIP_ALPHA = 150
HEADLINE_SPACING = 0.98


def _draw_footer_strip(
    base: Image.Image, text: str, height: int, font_size: int
) -> None:
    width, canvas_height = base.size
    top = canvas_height - height
    strip = Image.new("RGBA", (width, height), theme.INK_EDGE + (FOOTER_STRIP_ALPHA,))
    base.alpha_composite(strip, (0, top))
    font = theme.load_font(theme.FONT_MEDIUM, font_size)
    text_width = font.getlength(text)
    draw.draw_plain_text(
        base,
        text,
        font,
        (round((width - text_width) / 2), top + (height - font_size) // 2),
        theme.CREAM,
    )


def _draw_artwork_area(
    base: Image.Image, box: draw.Box, images: ArtworkImages
) -> None:
    """One panel, two panels, or the empty dashed frame."""
    left, top, right, bottom = box
    if len(images) >= 2:
        half = (right - left - PANEL_GAP) // 2
        draw.place_artwork(
            base, images[0][0], (left, top, left + half, bottom), images[0][1]
        )
        draw.place_artwork(
            base,
            images[1][0],
            (right - half, top, right, bottom),
            images[1][1],
        )
        return
    if len(images) == 1:
        draw.place_artwork(base, images[0][0], box, images[0][1])
        return
    draw.draw_dashed_frame(base, (left + 24, top + 24, right - 24, bottom - 24),
                           theme.GOLD)


def _render_facebook(data: CardData, images: ArtworkImages) -> Image.Image:
    width, height = theme.FACEBOOK_SIZE
    base = draw.make_background((width, height))

    art_box = (770, 0, width, height)
    _draw_artwork_area(base, art_box, images)
    draw.fade_edge(base, art_box, "left", theme.INK)

    draw.draw_trees(base, band_height=130)
    draw.draw_bulbs(base, (742, 30), (742, height - 30), count=10, radius=7)

    draw.draw_outlined_badge(
        base,
        data.badge,
        theme.load_font(theme.FONT_MEDIUM, 26),
        (64, 52),
        theme.GOLD,
    )

    lines, headline_font = draw.fit_text(
        data.headline, theme.FONT_BOLD,
        box_width=640, box_height=250, max_size=92, min_size=44,
    )
    y = draw.draw_glow_text(
        base, lines, headline_font, (64, 150), HEADLINE_SPACING,
        theme.CREAM, theme.GOLD,
    )

    y = draw.draw_plain_text(
        base, data.date_line, theme.load_font(theme.FONT_MEDIUM, 30),
        (64, y + 28), theme.GOLD,
    )
    draw.draw_plain_text(
        base, data.wordmark, theme.load_font(theme.FONT_BOLD, 30),
        (64, y + 16), theme.GOLD,
    )

    _draw_footer_strip(base, data.footer, height=52, font_size=22)
    return base


def _render_instagram(data: CardData, images: ArtworkImages) -> Image.Image:
    width, height = theme.INSTAGRAM_SIZE
    base = draw.make_background((width, height))

    band_bottom = 600
    art_box = (0, 0, width, band_bottom)
    _draw_artwork_area(base, art_box, images)
    draw.fade_edge(base, art_box, "bottom", theme.INK)

    draw.draw_trees(base, band_height=150)
    draw.draw_bulbs(
        base, (40, band_bottom), (width - 40, band_bottom), count=10, radius=8
    )

    draw.draw_outlined_badge(
        base,
        data.badge,
        theme.load_font(theme.FONT_MEDIUM, 30),
        (56, 44),
        theme.GOLD,
    )

    lines, headline_font = draw.fit_text(
        data.headline, theme.FONT_BOLD,
        box_width=968, box_height=230, max_size=88, min_size=44,
    )
    y = draw.draw_glow_text(
        base, lines, headline_font, (56, 660), HEADLINE_SPACING,
        theme.CREAM, theme.GOLD,
    )

    y = draw.draw_plain_text(
        base, data.date_line, theme.load_font(theme.FONT_MEDIUM, 32),
        (56, y + 28), theme.GOLD,
    )
    draw.draw_plain_text(
        base, data.wordmark, theme.load_font(theme.FONT_BOLD, 32),
        (56, y + 16), theme.GOLD,
    )

    _draw_footer_strip(base, data.footer, height=60, font_size=24)
    return base


def render(
    card_data: CardData, platform: str, images: ArtworkImages
) -> bytes:
    """Render one card to PNG bytes."""
    if platform == FACEBOOK:
        canvas = _render_facebook(card_data, images)
    elif platform == INSTAGRAM:
        canvas = _render_instagram(card_data, images)
    else:
        raise ValueError(f"unknown platform: {platform}")
    buffer = BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
```

- [ ] **Step 4: Write the package entry point**

Replace `cinema/social_cards/__init__.py`:

```python
"""Social card rendering for Fort Kent Cinema engagements.

    png = render_card(engagement, FACEBOOK)

Layers: card.py decides *what* goes on the card, posters.py fetches the
artwork, draw.py provides primitives, layouts.py places everything.
"""

from __future__ import annotations

import datetime

from cinema.models import Engagement

from .card import (
    BADGE_BY_PARAM,
    BADGE_COMING_SOON,
    BADGE_NOW_PLAYING,
    BADGE_SLUGS,
    FACEBOOK,
    INSTAGRAM,
    PARAM_BY_BADGE,
    PLATFORMS,
    CardData,
    default_badge,
)
from .layouts import render
from .posters import fetch_artwork

__all__ = [
    "BADGE_BY_PARAM",
    "BADGE_COMING_SOON",
    "BADGE_NOW_PLAYING",
    "BADGE_SLUGS",
    "FACEBOOK",
    "INSTAGRAM",
    "PARAM_BY_BADGE",
    "PLATFORMS",
    "CardData",
    "card_filename",
    "default_badge",
    "fetch_artwork",
    "render_card",
]


def card_filename(card_data: CardData, platform: str) -> str:
    badge_slug = BADGE_SLUGS[card_data.badge]
    return f"fkc-{card_data.slug}-{badge_slug}-{platform}.png"


def render_card(
    engagement: Engagement,
    platform: str,
    badge: str | None = None,
    today: datetime.date | None = None,
) -> tuple[bytes, str]:
    """Render a social card for `engagement`, with its download filename.

    Returns both so callers never rebuild CardData just to name the file.
    Never raises on artwork failure — a card without art still renders.
    """
    data = CardData.from_engagement(engagement, platform, badge, today)
    images = []
    for artwork in data.artwork:
        image = fetch_artwork(artwork.url)
        if image is not None:
            images.append((image, artwork.crop_bias))
    return render(data, platform, images), card_filename(data, platform)
```

The tests patch `cinema.social_cards.fetch_artwork`, which is why it is imported
into the package namespace and called unqualified here.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python manage.py test cinema.tests.test_social_cards_layouts -v 2`
Expected: PASS (13 tests)

- [ ] **Step 6: Eyeball the output**

The tests prove the pixels are non-uniform, not that the card looks right. Render one and look at it:

```bash
.venv/bin/python - <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fortkentcinema.settings")
django.setup()
import datetime
from cinema.social_cards import render_card, FACEBOOK, INSTAGRAM
from cinema.social_cards.card import CardData, Artwork, BADGE_NOW_PLAYING
from cinema.social_cards.layouts import render
from cinema.social_cards.posters import fetch_artwork

data = CardData(
    badge=BADGE_NOW_PLAYING,
    headline="THE SUPER MARIO GALAXY MOVIE",
    date_line="NOW THROUGH AUGUST 14",
    artwork=(),
    slug="mario",
)
poster = fetch_artwork(
    "https://image.tmdb.org/t/p/w500/dQFwdkCpfc5UOdQigYKQm06VJS4.jpg"
)
pairs = [(poster, 0.25)] if poster else []
for platform in (FACEBOOK, INSTAGRAM):
    out = f"/tmp/fkc-{platform}.png"
    open(out, "wb").write(render(data, platform, pairs))
    print(out)
PY

open /tmp/fkc-facebook.png /tmp/fkc-instagram.png
```

Compare against `~/Desktop/fkc-thumbnail-template-blank.png`. Tune the numbers in `theme.py` and the geometry constants in `layouts.py` until it matches. **This step is expected to take a few iterations — that is the point of it.** Re-run the layout tests after any change.

- [ ] **Step 7: Run the whole cinema suite and commit**

```bash
.venv/bin/python manage.py test cinema -v 2
.venv/bin/python -m flake8 cinema/social_cards cinema/tests
git add cinema/social_cards cinema/tests/test_social_cards_layouts.py
git commit -m "feat(cinema): Facebook and Instagram social card layouts"
```

---

### Task 7: The download view

**Files:**
- Modify: `dashboard/views.py` (add import + new view class at the end)
- Modify: `dashboard/urls.py`
- Test: `dashboard/tests/test_social_cards.py`

**Interfaces:**
- Consumes: `cinema.social_cards.{render_card, card_filename, CardData, PLATFORMS, BADGE_BY_PARAM}`.
- Produces:
  - URL name `dashboard:engagement_social_card`, args `(pk, platform)`
  - `dashboard.views.EngagementSocialCardView`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_social_cards.py`:

```python
import datetime
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from cinema.models import Engagement, EngagementFilm, Film, Screen

User = get_user_model()


def an_image() -> Image.Image:
    return Image.new("RGB", (400, 600), (200, 40, 40))


class SocialCardViewTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(
            title="Dune", poster_url="https://image.tmdb.org/t/p/w500/d.jpg"
        )
        self.eng = Engagement.objects.create(
            screen=self.screen,
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
        )
        EngagementFilm.objects.create(
            engagement=self.eng, film=self.film, position=1
        )
        patcher = mock.patch(
            "cinema.social_cards.fetch_artwork", return_value=an_image()
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def url(self, platform: str = "instagram", **params: str) -> str:
        base = reverse(
            "dashboard:engagement_social_card", args=[self.eng.pk, platform]
        )
        if not params:
            return base
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base}?{query}"

    def test_returns_a_png(self) -> None:
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(Image.open(BytesIO(response.content)).size, (1080, 1080))

    def test_facebook_dimensions(self) -> None:
        response = self.client.get(self.url("facebook"))
        self.assertEqual(Image.open(BytesIO(response.content)).size, (1200, 630))

    def test_served_inline_by_default(self) -> None:
        response = self.client.get(self.url())
        self.assertIn("inline", response["Content-Disposition"])

    def test_download_param_forces_an_attachment(self) -> None:
        response = self.client.get(self.url("instagram", download="1"))
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(
            'filename="fkc-dune-now-playing-instagram.png"',
            response["Content-Disposition"],
        )

    def test_badge_param_is_honoured(self) -> None:
        response = self.client.get(
            self.url("facebook", badge="coming_soon", download="1")
        )
        self.assertIn(
            'filename="fkc-dune-coming-soon-facebook.png"',
            response["Content-Disposition"],
        )

    def test_unrecognised_badge_falls_back_to_the_default(self) -> None:
        response = self.client.get(
            self.url("facebook", badge="whenever", download="1")
        )
        self.assertIn("now-playing", response["Content-Disposition"])

    def test_unknown_platform_is_a_400(self) -> None:
        response = self.client.get(
            reverse(
                "dashboard:engagement_social_card", args=[self.eng.pk, "tiktok"]
            )
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_engagement_is_a_404(self) -> None:
        response = self.client.get(
            reverse("dashboard:engagement_social_card", args=[9999, "facebook"])
        )
        self.assertEqual(response.status_code, 404)

    def test_anonymous_users_are_redirected(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code, 302)

    def test_non_staff_users_are_forbidden(self) -> None:
        User.objects.create_user(username="u", password="pw12345")
        self.client.logout()
        self.client.login(username="u", password="pw12345")
        self.assertEqual(self.client.get(self.url()).status_code, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python manage.py test dashboard.tests.test_social_cards -v 2`
Expected: FAIL — `NoReverseMatch: Reverse for 'engagement_social_card' not found`

- [ ] **Step 3: Add the view**

In `dashboard/views.py`, add to the imports at the top:

```python
from cinema.social_cards import BADGE_BY_PARAM, PLATFORMS, render_card
from django.http import HttpResponseBadRequest
```

`HttpResponse` is already imported; extend that line rather than duplicating it.

Append to the end of `dashboard/views.py`:

```python
class EngagementSocialCardView(StaffRequiredMixin, View):
    """Render an engagement's promo image as a PNG.

    Served inline for the dashboard preview; with ?download=1 as an
    attachment for the download buttons.
    """

    def get(self, request, pk: int, platform: str) -> HttpResponse:
        if platform not in PLATFORMS:
            return HttpResponseBadRequest("Unknown platform")
        engagement = get_object_or_404(
            Engagement.objects.prefetch_related("engagement_films__film"),
            pk=pk,
        )
        badge = BADGE_BY_PARAM.get(request.GET.get("badge", ""))
        png, filename = render_card(engagement, platform, badge)
        disposition = "attachment" if "download" in request.GET else "inline"

        response = HttpResponse(png, content_type="image/png")
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response
```

- [ ] **Step 4: Add the route**

In `dashboard/urls.py`, add after the `engagement_status` line:

```python
    path(
        "engagements/<int:pk>/social/<slug:platform>.png",
        views.EngagementSocialCardView.as_view(),
        name="engagement_social_card",
    ),
```

The `slug` converter is used deliberately: its pattern excludes `.`, so the
literal `.png` suffix cannot be swallowed by the parameter.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python manage.py test dashboard.tests.test_social_cards -v 2`
Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add dashboard/views.py dashboard/urls.py dashboard/tests/test_social_cards.py
git commit -m "feat(dashboard): social card download endpoint"
```

---

### Task 8: The Social Images panel

**Files:**
- Create: `dashboard/templates/dashboard/_social_cards.html`
- Create: `dashboard/static/dashboard/css/social_cards.css`
- Modify: `dashboard/templates/dashboard/engagement_detail.html`
- Modify: `dashboard/views.py` (`EngagementDetailView.get_context_data`)
- Modify: `dashboard/tests/test_social_cards.py` (append)

**Interfaces:**
- Consumes: `dashboard:engagement_social_card`, `cinema.social_cards.{default_badge, PARAM_BY_BADGE, FACEBOOK, INSTAGRAM}`.
- Produces: context keys `social_default_badge`, `social_facebook_url`, `social_instagram_url`.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_social_cards.py`:

```python
class SocialPanelTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune")

    def make_eng(self, start: datetime.date, end: datetime.date) -> Engagement:
        eng = Engagement.objects.create(
            screen=self.screen, start_date=start, end_date=end
        )
        EngagementFilm.objects.create(engagement=eng, film=self.film, position=1)
        return eng

    def detail_html(self, eng: Engagement) -> str:
        return self.client.get(
            reverse("dashboard:engagement_detail", args=[eng.pk])
        ).content.decode()

    def test_panel_is_rendered(self) -> None:
        eng = self.make_eng(
            datetime.date(2026, 7, 1), datetime.date(2026, 7, 7)
        )
        html = self.detail_html(eng)
        self.assertIn("Social Images", html)
        self.assertIn("Coming Soon", html)
        self.assertIn("Now Playing", html)

    def test_panel_links_to_both_platforms(self) -> None:
        eng = self.make_eng(
            datetime.date(2026, 7, 1), datetime.date(2026, 7, 7)
        )
        html = self.detail_html(eng)
        for platform in ("facebook", "instagram"):
            self.assertIn(
                reverse(
                    "dashboard:engagement_social_card", args=[eng.pk, platform]
                ),
                html,
            )

    def test_future_run_defaults_to_coming_soon(self) -> None:
        today = datetime.date.today()
        eng = self.make_eng(
            today + datetime.timedelta(days=30),
            today + datetime.timedelta(days=37),
        )
        response = self.client.get(
            reverse("dashboard:engagement_detail", args=[eng.pk])
        )
        self.assertEqual(response.context["social_default_badge"], "coming_soon")

    def test_current_run_defaults_to_now_playing(self) -> None:
        today = datetime.date.today()
        eng = self.make_eng(
            today - datetime.timedelta(days=2),
            today + datetime.timedelta(days=2),
        )
        response = self.client.get(
            reverse("dashboard:engagement_detail", args=[eng.pk])
        )
        self.assertEqual(response.context["social_default_badge"], "now_playing")


class SocialCardCssTests(TestCase):
    def test_stylesheet_exists(self) -> None:
        from pathlib import Path

        from django.conf import settings

        path = (
            Path(settings.BASE_DIR)
            / "dashboard/static/dashboard/css/social_cards.css"
        )
        self.assertIn(".socialPreview", path.read_text())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python manage.py test dashboard.tests.test_social_cards -v 2`
Expected: FAIL — `AssertionError: 'Social Images' not found in ...`

- [ ] **Step 3: Add the context keys**

In `dashboard/views.py`, extend the imports from `cinema.social_cards`:

```python
from cinema.social_cards import (
    BADGE_BY_PARAM,
    FACEBOOK,
    INSTAGRAM,
    PARAM_BY_BADGE,
    PLATFORMS,
    default_badge,
    render_card,
)
```

In `EngagementDetailView.get_context_data`, before `return ctx`:

```python
        ctx["social_default_badge"] = PARAM_BY_BADGE[default_badge(engagement)]
        ctx["social_facebook_url"] = reverse(
            "dashboard:engagement_social_card", args=[engagement.pk, FACEBOOK]
        )
        ctx["social_instagram_url"] = reverse(
            "dashboard:engagement_social_card", args=[engagement.pk, INSTAGRAM]
        )
```

`reverse` is already imported in `dashboard/views.py`.

- [ ] **Step 4: Create the panel template**

Create `dashboard/templates/dashboard/_social_cards.html`:

```html
<div class="card socialCards" x-data="{ badge: '{{ social_default_badge }}' }">
  <h2 class="cardTitle">Social Images</h2>

  <div class="badgeToggle" role="radiogroup" aria-label="Card headline">
    <label class="badgeOption">
      <input type="radio" name="social-badge" value="coming_soon" x-model="badge" />
      <span>Coming Soon</span>
    </label>
    <label class="badgeOption">
      <input type="radio" name="social-badge" value="now_playing" x-model="badge" />
      <span>Now Playing</span>
    </label>
  </div>

  <img
    class="socialPreview"
    :src="'{{ social_instagram_url }}?badge=' + badge"
    alt="Instagram preview for {{ engagement.display_title }}"
  />

  <div class="socialActions">
    <a class="btn-primary"
       :href="'{{ social_facebook_url }}?badge=' + badge + '&download=1'">
      Download for Facebook
    </a>
    <a class="btn-primary"
       :href="'{{ social_instagram_url }}?badge=' + badge + '&download=1'">
      Download for Instagram
    </a>
  </div>

  <p class="socialHint">
    Facebook is 1200&times;630, Instagram is 1080&times;1080. The preview shows
    the Instagram square.
  </p>
</div>
```

String concatenation is used rather than template literals: backticks inside a
Django-rendered attribute are easy to get wrong, and `+` reads the same.

- [ ] **Step 5: Include the panel**

In `dashboard/templates/dashboard/engagement_detail.html`, insert immediately before `<section class="showtimesSection">`:

```html
  {% include "dashboard/_social_cards.html" %}
```

And add the stylesheet in `{% block head_extra %}`, which currently holds one link:

```html
{% block head_extra %}<link rel="stylesheet" href="{% static 'dashboard/css/engagement_detail.css' %}" /><link rel="stylesheet" href="{% static 'dashboard/css/social_cards.css' %}" />{% endblock %}
```

- [ ] **Step 6: Create the stylesheet**

Create `dashboard/static/dashboard/css/social_cards.css`:

```css
/* Social Images panel on the engagement detail page. */

.socialCards {
  margin-bottom: 1.5rem;
}

.badgeToggle {
  display: flex;
  gap: 1.25rem;
  margin-bottom: 1rem;
}

.badgeOption {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.badgeOption input {
  accent-color: var(--brass);
}

.socialPreview {
  display: block;
  width: 100%;
  max-width: 420px;
  aspect-ratio: 1 / 1;
  border-radius: 6px;
  border: 1px solid rgba(13, 13, 13, 0.12);
  background: var(--surface-secondary);
  object-fit: cover;
}

.socialActions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
}

.socialHint {
  margin: 0.75rem 0 0;
  font-size: 0.8125rem;
  color: var(--text-tertiary);
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/bin/python manage.py test dashboard.tests.test_social_cards -v 2`
Expected: PASS (16 tests)

- [ ] **Step 8: Check it in the browser**

```bash
.venv/bin/python manage.py runserver
```

Open an engagement detail page, confirm the preview loads, toggle the badge and
confirm the preview and both button URLs update, then click each download button
and check the saved filenames.

- [ ] **Step 9: Full suite, lint, commit**

```bash
.venv/bin/python manage.py test
.venv/bin/python -m flake8 cinema dashboard
.venv/bin/python -m mypy cinema/social_cards dashboard/views.py
git add dashboard cinema
git commit -m "feat(dashboard): Social Images panel on engagement detail"
```

`mypy` may report pre-existing issues elsewhere in `dashboard/views.py`; only
fix what this work introduced.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
| --- | --- |
| Rendering approach (Pillow, vendored fonts) | 1 |
| Module layout | 1–6 |
| Badge default and override | 2, 7 |
| Headline, auto-fit, gold last line | 2, 4, 6 |
| Date line incl. single-day | 2 |
| Fixed wordmark and footer | 2, 6 |
| Artwork source selection, backdrop preference, top-bias | 2 |
| Artwork resolution, guards, cache | 3 |
| Empty-artwork dashed frame | 5, 6 |
| Facebook and Instagram geometry | 6 |
| Two-panel split | 2, 5, 6 |
| Glow | 4 |
| URL, params, disposition, filename | 7 |
| Staff gating, 400, 404 | 7 |
| Dashboard panel, toggle, preview | 8 |
| Test plan | every task |

**Placeholder scan:** none — every step carries the code it needs.

**Type consistency:** `Artwork(url, crop_bias)`, `CardData(badge, headline, date_line, artwork, slug, wordmark, footer)`, `render(card_data, platform, images)` where `images` is `Sequence[tuple[Image.Image, float]]`, `render_card(engagement, platform, badge=None, today=None) -> bytes`, and `card_filename(card_data, platform) -> str` are used identically wherever they appear. `Box` is `tuple[int, int, int, int]` throughout. `BADGE_BY_PARAM` (underscores, for query params) and `BADGE_SLUGS` (hyphens, for filenames) are kept distinct in Tasks 2, 7, and 8.
