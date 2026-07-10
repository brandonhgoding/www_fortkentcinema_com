# Dashboard Port — Films + TMDB + FilmSearch — Design

**Date:** 2026-07-06
**Status:** Approved (design phase)
**Repo:** `api_fortkentcinema_com` (branch `feat/dashboard`)

## Context

Sub-project 3 of the leprinceos dashboard port. The Engagements create/edit drawer (sub-project 4) needs a **film picker**: the React `FilmSearchCombo` searches existing films *and* The Movie Database (TMDB), and imports a `Film` from a TMDB result inline. fortkentcinema has no TMDB integration. This sub-project builds that infrastructure — a TMDB service, film search + import endpoints, and the combobox as an Alpine/HTMX component — so Engagements can consume it. It ends with a working, tested film picker; the Engagements page itself is sub-project 4.

Source: `www_leprinceos_com/src/components/FilmSearchCombo/FilmSearchCombo.tsx` (+ `.module.css`), `src/api/films.ts`; and the leprinceos backend `api_leprinceos_com/films/tmdb/{client,services}.py`.

## Cross-cutting decisions (inherited)

Server-rendered Django + HTMX + Alpine; verbatim CSS ports; `is_staff` gate; reuse Foundation Toast/Confirm/Drawer primitives; CSRF is already wired globally (`hx-headers` on `<body>`). Dashboard-authored styles live in `dashboard/static/dashboard/css/dashboard.css`.

## Decisions (this sub-project)

- **TMDB module home:** `cinema/tmdb/` (Film-domain logic, mirroring the source's `films/tmdb/`). This sub-project therefore extends the `cinema` app — a deliberate, scoped exception to the "dashboard-only" rule.
- **Import dedupe:** importing from TMDB reuses an existing `cinema.Film` with the same `tmdb_id` (idempotent) rather than erroring or duplicating.
- **Key handling:** `TMDB_API_KEY` from env (default `""`). Tests mock `requests`; no key needed to build/test. Live search + browser verification need a real key in `.env` (gitignored).

## Architecture

### TMDB service (`cinema/tmdb/`)

Verbatim port of the leprinceos service:
- `client.py` — `TMDBClient` (`search_movies`, `get_movie_details`, `build_image_url`) + `TMDBAPIError`; `requests` with a 10s timeout; reads `settings.TMDB_API_KEY`/`TMDB_BASE_URL`/`TMDB_IMAGE_BASE_URL`; raises `ValueError` if no key.
- `services.py` — `TMDBService` wrapping the client: `search_films(query, page=1)` (cached 5 min via `django.core.cache`, normalized dicts: `tmdb_id`, `title`, `release_date`, `overview`, `poster_path` (full URL), `backdrop_path`, `runtime`, `genres`, `vote_average`, `popularity`) and `get_film_details(tmdb_id)` (adds `runtime`, `genres`, `imdb_id`).
- Settings appended to `fortkentcinema/settings.py`: `TMDB_API_KEY = config("TMDB_API_KEY", default="")`, `TMDB_BASE_URL = "https://api.themoviedb.org/3"`, `TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/"`.

Tests mock `requests.get` (success, HTTP error → `TMDBAPIError`, non-JSON) mirroring the leprinceos tests, plus the service normalization + cache behavior.

### Film selectors + import

A small `cinema`-facing helper (or reuse the model directly) to create-or-reuse a Film from normalized TMDB details:
- `import_film_from_tmdb(tmdb_id) -> Film`: if a `Film` with that `tmdb_id` exists, return it; else `get_film_details` → create `Film(title, tmdb_id=str, poster_url=poster_path, backdrop_url=backdrop_path, overview, runtime_minutes=runtime, imdb_id)`. (The `Film.save()` empty-string→None coercion already handles blank ids.)

### Endpoints (`dashboard`, staff-gated, `/dashboard/films/`)

All return HTML fragments (HTMX), all `StaffRequiredMixin`:
- `GET films/search?q=` → `_film_options.html`: local `Film.objects.filter(title__icontains=q)[:limit]` rendered as dropdown options, followed by a "Search TMDB for '<q>'" action button (`hx-get` the TMDB endpoint). Empty `q` → empty fragment.
- `GET films/search/tmdb?q=` → `_tmdb_options.html`: `TMDBService().search_films(q)` rendered as options (poster thumb `w92`, title, release year). On `TMDBAPIError` or missing key → a small inline error row (not a 500).
- `POST films/from-tmdb` (body `tmdb_id`) → `import_film_from_tmdb`, then respond with an `HX-Trigger` `film-selected` event (payload: the film's id/title/poster) so the host form adds it; plus a success toast. On error → error toast, no film added.

### FilmSearchCombo (Alpine + HTMX partial)

`_film_search_combo.html` + `FilmSearchCombo.module.css` (verbatim) + an Alpine component in `dashboard.js`:
- Debounced search input: `hx-get="…/films/search" hx-trigger="keyup changed delay:300ms, focus" hx-target="<the dropdown>"`.
- Dropdown lists local film options → the "Search TMDB" button (which `hx-get`s the TMDB endpoint and appends results) → TMDB result options.
- Selecting a local option emits Alpine event `film-selected` with `{id,title,poster}`; selecting a TMDB option `hx-post`s `from-tmdb` (which fires the same `film-selected` trigger server-side).
- Keyboard nav (↑/↓/Enter/Esc) and click-outside close via a small Alpine `filmCombo` component; input clears after a selection.
- The combo is **reusable/parameterizable** (an id/name so multiple combos can coexist for double features) and host-agnostic: the consuming form (Engagements, sub-project 4) listens for `film-selected` to append to its selected-films list. No permanent demo route is shipped — the combo is verified by rendering the `_film_search_combo.html` partial and driving the search/tmdb/from-tmdb endpoints in tests. Sub-project 4 is the first real host.

## Testing

- **TMDB client** (`cinema/tmdb/tests/`): mock `requests.get` — search/details success, HTTP error → `TMDBAPIError` with status, non-JSON → error, `build_image_url` (None → "", path → full URL), missing key → `ValueError`.
- **TMDB service:** normalization of search vs details, 5-min cache hit (second call doesn't re-request), error propagation.
- **import_film_from_tmdb:** creates a Film from mocked details; second call with same tmdb_id reuses (no duplicate).
- **Endpoints** (`dashboard/tests/`): local search returns matching options + the TMDB button; empty q → empty; TMDB search fragment renders mocked results; TMDB error → inline error not 500; from-tmdb creates/reuses + fires `film-selected` HX-Trigger + toast; staff gate.
- **Combo fragment:** renders the input + dropdown wiring; the `filmCombo` Alpine registration present in dashboard.js.

Browser/pixel verification (combo dropdown vs the React combobox, live TMDB search) after build, once a key is in `.env`.

## Out of scope

- The Engagements list/form/StatusDropdown (sub-project 4), EngagementDetail (5), Home (6).
- A standalone Films management page (films are created via TMDB import; a manual Film CRUD is not required by the source).
- Genres/vote fields on `cinema.Film` (the model has none; normalized TMDB genres/vote are used only for display in the picker, not persisted).

## Verification

- `python manage.py check` clean; `makemigrations --check` clean (no model changes — `cinema.Film` already has the needed fields).
- `dashboard` + `cinema` test suites green; full project suite green.
- Manual (needs `TMDB_API_KEY`): the combo searches local films, "Search TMDB" returns real results, importing one creates a Film and selects it; compare the dropdown against the React combobox.
