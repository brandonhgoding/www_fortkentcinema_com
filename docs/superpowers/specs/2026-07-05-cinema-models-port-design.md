# Cinema Models Port — Design

**Date:** 2026-07-05
**Status:** Approved (design phase)
**Repo:** `api_fortkentcinema_com` (branch `feat/cinema-models-port`)

## Goal

Port the showtimes/engagements domain models from the external
`api_leprinceos_com` (cinema_sass) project into `api_fortkentcinema_com` so the
data can eventually be served natively by Django instead of being consumed over
HTTP. This phase covers **models + Django admin only**. The frontend continues
to consume leprinceos over HTTP (`web/services/leprinceos.py`) and is ported
later.

## Background

`api_fortkentcinema_com` is the server-rendered Django site for
www.fortkentcinema.com. It currently fetches showtimes/engagements from the
leprinceos API server-side with a short-TTL cache. leprinceos is single-cinema
per deploy (no schema-based multitenancy — `SiteConfig` is a `pk=1` singleton),
so the models port cleanly with no tenant scoping to strip.

Source models (leprinceos):

- `films` app — `Film`
- `cinemas` app — `Screen`, `SiteConfig`
- `engagements` app — `Engagement`, `EngagementFilm` (M2M through-model)
- `showtimes` app — `Showtime`

Dependency graph:

```
Showtime ── FK ──▶ Engagement (CASCADE)
Showtime ── FK ──▶ Screen (PROTECT)
Engagement ── M2M via EngagementFilm ──▶ Film
Engagement ── FK ──▶ Screen (PROTECT)
EngagementFilm ── FK ──▶ Engagement (CASCADE)
EngagementFilm ── FK ──▶ Film (PROTECT)
```

## Decisions

- **App layout:** consolidate all ported models into a single new Django app
  named `cinema` (rather than mirroring the 4 source apps or folding into `web`).
- **Fidelity:** verbatim port — keep every field, choice, index,
  `UniqueConstraint`, property, and `save()`/`clean()` method unchanged.
- **Model set:** `Film`, `Screen`, `Engagement`, `EngagementFilm`, `Showtime`.
  **`SiteConfig` is dropped** — it is standalone, only used by leprinceos'
  `ActiveTimezoneMiddleware` (a frontend concern not in scope), and the target
  `web` app already has its own site-config concept.
- **Data:** empty tables. Populate via Django admin (or a later import). No data
  migration in this phase.

## App structure

Models live in a `models/` package (one model per file, mirroring source style):

```
cinema/
  __init__.py
  apps.py                  # CinemaConfig
  models/
    __init__.py            # re-exports Film, Screen, Engagement, EngagementFilm, Showtime
    film.py                # Film
    screen.py              # Screen
    engagement.py          # Engagement + EngagementStatus (module-level TextChoices)
    engagement_film.py     # EngagementFilm
    showtime.py            # Showtime
  admin.py                 # all registrations + inlines
  migrations/
    __init__.py
    0001_initial.py        # generated
```

## Models — verbatim port

All fields/choices/indexes/constraints/properties/`save()`/`clean()` carried over
unchanged. The **only** mechanical edits, required by consolidating four apps
into one app label `cinema`:

- `Engagement.films = ManyToManyField(Film, through="engagements.EngagementFilm", …)`
  → `through="cinema.EngagementFilm"`
- `EngagementFilm.engagement = ForeignKey("engagements.Engagement", …)`
  → `ForeignKey("cinema.Engagement", …)`
- Cross-app imports (`from cinemas.models import Screen`,
  `from films.models import Film`, `from engagements.models import Engagement`)
  become intra-app imports.

`on_delete` semantics preserved: CASCADE for `Engagement→Showtime` and
`Engagement→EngagementFilm`; PROTECT for all `→Screen` and `→Film`.

Preserved behavior worth calling out:

- `Film.save()` coerces empty-string `tmdb_id`/`imdb_id`/`youtube_id` to `None`
  (so the `unique` constraints allow multiple blanks).
- `Showtime.save()` defaults `screen_id` from its engagement when unset.
- `Engagement.clean()` rejects `end_date < start_date`.
- Properties: `display_title`, `is_active`, `is_free_for_members`,
  `ordered_films`, `primary_film`, `total_runtime_minutes`,
  `Showtime.is_outside_engagement_range`, `Engagement.default_visibility_for`.

The empty `films/genre.py` (no model) is not ported.

## Admin — with inlines

The source registers each model flat. This port upgrades the Engagement admin to
use inlines for its relations:

- `EngagementFilmInline` (`TabularInline`, ordered by `position`) — attach and
  order films directly on the engagement page.
- `ShowtimeInline` (`TabularInline`) — manage a run's showtimes inline.
- `EngagementAdmin` keeps source `list_display` / `list_filter` /
  `date_hierarchy` / `search_fields`, plus the two inlines.

Standalone registrations retained (ported from source):

- `FilmAdmin` — `list_display=(title, rating, runtime_minutes, created_at)`,
  `search_fields`, `list_filter=(rating,)`.
- `ScreenAdmin` — `list_display=(name, capacity)`.
- `ShowtimeAdmin` — source `list_display`/`list_filter`/`date_hierarchy`/
  `search_fields` (lets you browse/bulk-edit showtimes outside an engagement).

`EngagementFilm` is managed only through the inline (no standalone registration).

## Wiring & migrations

- Add `"cinema.apps.CinemaConfig"` to `INSTALLED_APPS`.
- `python manage.py makemigrations cinema` → single `0001_initial`.
- `python manage.py migrate` → creates empty tables.

## Out of scope (this phase)

- Frontend/template changes. `web/services/leprinceos.py` keeps serving the site
  over HTTP, untouched. The new models sit alongside, ready to become the source
  of truth later.
- Selectors, services, `warnings.py`, TMDB integration, API endpoints/serializers.
- Data import from the leprinceos DB.

## Verification

- `python manage.py makemigrations --check` clean after generation.
- `python manage.py migrate` applies without error.
- `python manage.py check` passes.
- Admin smoke test: create a Screen, Film, then an Engagement with a film + a
  showtime via the inlines; confirm `display_title`, the `unique` constraints,
  and `Showtime.save()` screen defaulting behave as expected.
