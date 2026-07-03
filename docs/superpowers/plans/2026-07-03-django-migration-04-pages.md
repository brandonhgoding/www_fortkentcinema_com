# Django Migration — Plan 4: Remaining Pages + Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the four remaining routes — `/membership`, `/rentals`, `/about`, `/classics` — and complete the Coming Soon section by adding its calendar view (the grid↔calendar toggle + HTMX month navigation deferred from Plan 2). After this, every nav link resolves to a real server-rendered page.

**Architecture:** Membership/Rentals/About are static `TemplateView`s rendering ported markup (Membership loops the already-ported `MEMBERSHIP` constant + a new `MEMBERSHIP_FAQ`). Classics is a `TemplateView` backed by a new `get_classic_movie_night()` in the leprinceos service (same cached/guarded pattern as `get_now_showing`), with Alpine driving the expand/trailer. The Coming Soon calendar adds a new `get_calendar_month()` service and an HTMX fragment endpoint (`/calendar/<year>/<month>`) that returns a month grid with prev/next navigation; Alpine toggles grid vs calendar.

**Tech Stack:** Django 5.2.3 class-based views + templates, the leprinceos service (`requests`/`zoneinfo`/cache), HTMX (calendar month nav), Alpine (view toggle, expand). Tests: Django `unittest` (service mocked).

## Global Constraints

- Target repo: `api_fortkentcinema_com`, branch `feat/django-frontend-migration` (continues from Plans 1–3).
- Django 5.2.3; existing `api/` DRF surface untouched. Activate `.venv` for Django commands; `.env` (gitignored, `DEBUG=True`) auto-loads.
- Markup preserves **every CSS class name + DOM structure** from the source React component (pixel-identical bar). CSS is already in `static/css/` from Plan 1; page sheets link via `{% block extra_css %}`.
- Static config already ported: `web.constants.MEMBERSHIP` (a list of tier dicts: `id, slug, name, eyebrow?, price, duration_months, is_family_tier, featured, perks[list of str], checkout_url`). This task adds `MEMBERSHIP_FAQ`.
- leprinceos service (`web/services/leprinceos.py`) already exists with `_get` (cache + `raise_for_status` + stale fallback), `_format_showtime`, `_local_date`, `_format_runtime`, `_primary_film_id`, and per-record transform guards. New fetchers follow the SAME pattern (guarded, cached, snake_case output).
- Interactivity: **Alpine** for the classics expand + coming-soon view toggle; **HTMX** for the calendar month navigation (server-rendered fragments). Effects grids use `data-spotlight` (cards are `<article>` or `<a>`; `cardSpotlight.js` matches `:scope > article, :scope > a`).
- Multi-line template comments use `{% comment %}` (a multi-line `{# #}` leaks). The `test_no_template_comment_leaks_into_page` guard exists for home; keep new templates clean.
- All routes for these pages go in `web.urls` (they're `web` app pages), mounted at `/`. The calendar fragment endpoint also goes in `web.urls`.
- TDD: failing test first each task. Commit after each green task. SPA source: `/Users/bgoding/code/SoftwareMaine/www_fortkentcinema_com`.

---

### Task 1: Membership page (`/membership`)

Static page composing Hero, Benefits (4 inline-SVG cards), Tiers (loops `MEMBERSHIP` → tier cards), FAQ (loops a new `MEMBERSHIP_FAQ`), and a final CTA. The "view memberships"/"choose your tier" buttons are anchor links to the tiers section (`#tiers`).

**Files:**
- Create: `web/templates/web/membership.html`, `templates/partials/tier_card.html`
- Modify: `web/views.py` (`MembershipView`), `web/urls.py` (route), `web/constants.py` (add `MEMBERSHIP_FAQ`), `web/tests/test_pages.py`
- Reference: SPA `src/pages/MembershipPage.jsx`, `src/components/Membership/{MembershipHero,MembershipBenefits,MembershipTiers,MembershipFAQ,TierCard}.jsx`, `src/data/membershipFaq.json`

**Interfaces:**
- Consumes: `web.constants.MEMBERSHIP`, `web.constants.MEMBERSHIP_FAQ`.
- Produces: URL name `membership` at `membership/`; `MembershipView(TemplateView)` with context `tiers=MEMBERSHIP`, `faqs=MEMBERSHIP_FAQ`; `partials/tier_card.html` rendering one `tier`.

- [ ] **Step 1: Write the failing test**

Add to `web/tests/test_pages.py`:

```python
class MembershipPageTests(TestCase):
    def test_membership_200_and_template(self):
        resp = self.client.get(reverse("membership"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "web/membership.html")

    def test_renders_tiers_and_faq(self):
        html = self.client.get(reverse("membership")).content.decode()
        self.assertIn("Silver Screen", html)       # a tier name from MEMBERSHIP
        self.assertIn("tier-card", html)
        self.assertIn("membership-faq", html)
        self.assertIn("How long does a membership last?", html)  # a FAQ question
        self.assertIn('id="tiers"', html)          # scroll-to anchor target

    def test_membership_meta(self):
        html = self.client.get(reverse("membership")).content.decode()
        self.assertIn("Membership", html)
```

- [ ] **Step 2: Run → fail** (`membership` route missing).

Run: `source .venv/bin/activate && python manage.py test web.tests.test_pages`

- [ ] **Step 3: Add `MEMBERSHIP_FAQ` constant**

Read `src/data/membershipFaq.json` and transcribe it into `web/constants.py` as `MEMBERSHIP_FAQ = [{"question": ..., "answer": ...}, ...]` (5 entries, verbatim).

- [ ] **Step 4: Add the view + url**

`web/views.py`:

```python
from web.constants import MEMBERSHIP, MEMBERSHIP_FAQ


class MembershipView(TemplateView):
    template_name = "web/membership.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tiers"] = MEMBERSHIP
        ctx["faqs"] = MEMBERSHIP_FAQ
        return ctx
```

`web/urls.py` — add before the `home` route is fine (no conflict; distinct paths):

```python
    path("membership/", MembershipView.as_view(), name="membership"),
```

- [ ] **Step 5: Create the templates**

`web/templates/web/membership.html` — extend base, override meta (title "Membership — Fort Kent Cinema", description from MembershipPage.jsx Helmet). Transcribe the MembershipPage composition preserving classes: `membership-page`, then the sections from each sub-component:
- **Hero** (`membership-hero`, `__inner/__eyebrow/__title/__rule/__diamond/__subtitle/__cta`): the "View Memberships" button becomes `<a href="#tiers" class="btn btn-primary membership-hero__cta">`.
- **Benefits** (`membership-benefits`, `__header/__eyebrow/__title/__grid/__item/__medallion/__heading/__text`, `data-reveal` on the header): the 4 BENEFITS are static — transcribe the array (title, text, and the exact inline `<svg>` for each) into 4 `<li>` items verbatim.
- **Tiers** (`membership-tiers` `id="tiers"`, `__header/__eyebrow/__title/__grid`, `data-reveal` on header): loop `{% for tier in tiers %}{% include "partials/tier_card.html" %}{% endfor %}`.
- **FAQ** (`membership-faq`, `__header/__eyebrow/__title/__list/__item/__question/__diamond/__answer`): loop `faqs` into `<dt>`/`<dd>` pairs.
- **Final CTA** (`membership-page__final-cta`, `__final-cta-rule`): the "Choose your tier" button → `<a href="#tiers" class="btn btn-primary">`.
Link the sheets in `{% block extra_css %}`: `MembershipPage.css`, `MembershipHero.css`, `MembershipBenefits.css`, `MembershipTiers.css`, `MembershipFAQ.css`, `TierCard.css`.

`templates/partials/tier_card.html` — transcribe `TierCard.jsx` for the `perks` path (our tier data has `perks` = list of strings, no `benefits`/`scope`, so every perk uses the default **star** `ScopeIcon` and no `monthlyLimit` chip). Preserve classes (`tier-card`, `tier-card--featured`, `tier-card__ribbon(--featured/--family)`, `tier-card__header/__eyebrow/__name/__rule/__price/__price-period/__perks/__perk-icon/__perk-text/__cta`). Mapping:
- `{% if tier.featured %}tier-card--featured{% endif %}` on the article; ribbons: `{% if tier.featured %}<span class="tier-card__ribbon tier-card__ribbon--featured">Best Value</span>{% endif %}`, `{% if tier.is_family_tier %}<span class="tier-card__ribbon tier-card__ribbon--family">For Families</span>{% endif %}`.
- eyebrow: `{{ tier.eyebrow|default:"Patron Card" }}`; name; `${{ tier.price }}` (integer — the SPA does `Number(price).toFixed(0)`, and prices are whole numbers); `{{ tier.duration_months }}-month membership`.
- perks: `{% for perk in tier.perks %}<li><span class="tier-card__perk-icon" aria-hidden="true">`<the star SVG from ScopeIcon default>`</span><span class="tier-card__perk-text">{{ perk }}</span></li>{% endfor %}`.
- CTA: `<a href="{{ tier.checkout_url }}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary tier-card__cta">Join</a>`.

- [ ] **Step 6: Run → pass**, then full suite (Plan 3 was 59).

Run: `python manage.py test web.tests.test_pages && python manage.py test`

- [ ] **Step 7: Commit**

```bash
git add web/templates/web/membership.html templates/partials/tier_card.html web/views.py web/urls.py web/constants.py web/tests/test_pages.py
git commit -m "feat(web): /membership page (hero, benefits, tiers, FAQ, CTA)"
```

---

### Task 2: Rentals page (`/rentals`)

Fully static page — transcribe `PrivateRentalsPage.jsx` verbatim.

**Files:**
- Create: `web/templates/web/rentals.html`
- Modify: `web/views.py` (`RentalsView`), `web/urls.py`, `web/tests/test_pages.py`
- Reference: SPA `src/pages/PrivateRentalsPage.jsx` (read the WHOLE file)

**Interfaces:**
- Produces: URL name `rentals` at `rentals/`; `RentalsView(TemplateView)`, `template_name="web/rentals.html"`.

- [ ] **Step 1: Write the failing test**

```python
class RentalsPageTests(TestCase):
    def test_rentals_200_and_content(self):
        resp = self.client.get(reverse("rentals"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "web/rentals.html")
        html = resp.content.decode()
        self.assertIn("RENT THE THEATER", html)
        self.assertIn("$225", html)           # base rate
        self.assertIn("rentals-page", html)
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Add view + url**

```python
class RentalsView(TemplateView):
    template_name = "web/rentals.html"
```
`web/urls.py`: `path("rentals/", RentalsView.as_view(), name="rentals"),`

- [ ] **Step 4: Create `web/templates/web/rentals.html`**

Extend base; override meta (title/description/og from the Helmet in `PrivateRentalsPage.jsx`). Transcribe the ENTIRE `PrivateRentalsPage` markup verbatim, preserving every class (`rentals-page`, `rentals-container`, `rentals-header`, `rentals-back`, `rentals-title`, `rentals-subtitle`, `rentals-section`, `rentals-section-title`, `rentals-section-note`, `rentals-base`, `rental-card`, `rental-card--featured`, `rental-card-title/-price/-description/-features`, and whatever follows in the rest of the file). Replace `<Link to="/">` with `<a href="/">`, `<Link to="/xxx">` with `<a href="/xxx">`. Link `PrivateRentalsPage.css`.

- [ ] **Step 5: Run → pass**, then full suite.

- [ ] **Step 6: Commit**

```bash
git add web/templates/web/rentals.html web/views.py web/urls.py web/tests/test_pages.py
git commit -m "feat(web): /rentals page (static)"
```

---

### Task 3: About page (`/about`)

Fully static page — transcribe `AboutPage.jsx` verbatim (it already contains the real theater-history copy).

**Files:**
- Create: `web/templates/web/about.html`
- Modify: `web/views.py` (`AboutView`), `web/urls.py`, `web/tests/test_pages.py`
- Reference: SPA `src/pages/AboutPage/AboutPage.jsx` (read the WHOLE file)

**Interfaces:**
- Produces: URL name `about` at `about/`; `AboutView(TemplateView)`, `template_name="web/about.html"`.

- [ ] **Step 1: Write the failing test**

```python
class AboutPageTests(TestCase):
    def test_about_200_and_content(self):
        resp = self.client.get(reverse("about"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "web/about.html")
        html = resp.content.decode()
        self.assertIn("OUR STORY", html)
        self.assertIn("Savoy", html)     # from the real history copy
        self.assertIn("about-page", html)
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Add view + url**

```python
class AboutView(TemplateView):
    template_name = "web/about.html"
```
`web/urls.py`: `path("about/", AboutView.as_view(), name="about"),`

- [ ] **Step 4: Create `web/templates/web/about.html`**

Extend base; override meta from `AboutPage.jsx` Helmet. Transcribe the ENTIRE `AboutPage` markup verbatim, preserving all `about-*` classes and the full history copy. Replace `<Link>` with `<a href>`. Link `AboutPage.css`.

- [ ] **Step 5: Run → pass**, then full suite.

- [ ] **Step 6: Commit**

```bash
git add web/templates/web/about.html web/views.py web/urls.py web/tests/test_pages.py
git commit -m "feat(web): /about page (static, real history copy)"
```

---

### Task 4: Classics page (`/classics`) + `get_classic_movie_night()` service

Adds the leprinceos classics fetcher and the `/classics` page: hero, an empty state (film-reel SVG) when there are no screenings, the next screening, and an upcoming grid — each screening expandable (Alpine) to show synopsis + an inline trailer.

**Files:**
- Modify: `web/services/leprinceos.py` (add `get_classic_movie_night()`), `web/views.py` (`ClassicsView`), `web/urls.py`, `web/tests/test_leprinceos.py`, `web/tests/test_pages.py`
- Create: `web/templates/web/classics.html`
- Reference: SPA `src/services/api.js` (`getClassicMovieNight`), `src/pages/ClassicMoviePage/ClassicMoviePage.jsx`

**Interfaces:**
- Produces:
  - `get_classic_movie_night() -> dict` = `{"next_screening": <dict|None>, "upcoming": [<dict>]}`; each screening dict: `{"id": str, "title": str, "poster": str, "rating": str, "runtime": str, "synopsis": str, "youtube_id": str, "date": "YYYY-MM-DD", "display_date": "Weekday, Month D"}`. Same cached/guarded pattern as the other fetchers.
  - URL name `classics` at `classics/`; `ClassicsView(TemplateView)` with context `classics=get_classic_movie_night()`.

- [ ] **Step 1: Write the failing service test** (mock `requests.get`)

Add to `web/tests/test_leprinceos.py`:

```python
class GetClassicMovieNightTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_returns_next_and_upcoming_sorted(self):
        engagements = [{"id": 3, "kind": "CLASSIC", "display_title": "Casablanca",
                        "film_title": "Casablanca", "film_poster_url": "c.jpg",
                        "films": [{"id": 9}]}]
        showtimes = [
            {"id": 200, "starts_at": "2999-03-01T23:00:00Z"},
            {"id": 201, "starts_at": "2999-03-08T23:00:00Z"},
        ]
        film = {"rating": "PG", "runtime_minutes": 102, "synopsis": "A classic.", "youtube_id": "z"}

        def fake_get(url, timeout=None):
            if "/engagements/" in url:
                return _resp({"results": engagements})
            if "/showtimes/" in url:
                return _resp({"results": showtimes})
            if "/films/9" in url:
                return _resp(film)
            return _resp({"results": []})

        with mock.patch("web.services.leprinceos.requests.get", side_effect=fake_get):
            data = leprinceos.get_classic_movie_night()

        self.assertIsNotNone(data["next_screening"])
        self.assertEqual(data["next_screening"]["title"], "Casablanca")
        self.assertEqual(data["next_screening"]["synopsis"], "A classic.")
        self.assertEqual(len(data["upcoming"]), 1)          # 2 screenings: 1 next + 1 upcoming
        self.assertTrue(
            data["next_screening"]["date"] <= data["upcoming"][0]["date"]
        )

    def test_no_screenings(self):
        with mock.patch("web.services.leprinceos.requests.get",
                        return_value=_resp({"results": []})):
            data = leprinceos.get_classic_movie_night()
        self.assertEqual(data, {"next_screening": None, "upcoming": []})
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `get_classic_movie_night()`**

Port `getClassicMovieNight` from `api.js` (you have the pattern from the existing fetchers). Logic: fetch `/engagements/?kind=CLASSIC&status=CONFIRMED&end_date_after=<today>`; for each engagement fetch its showtimes + optional film detail; expand each showtime into a screening dict (snake_case keys per the Interfaces), computing `date` (`_local_date`) and `display_date` (Eastern, format `"Weekday, Month D"` — use `datetime.astimezone(CINEMA_TZ).strftime("%A, %B %-d")`); keep only screenings with `date >= today`; flatten + sort by `date`; return `{"next_screening": screenings[0] if screenings else None, "upcoming": screenings[1:]}`. Wrap per-record transforms in try/except (skip bad rows) and the whole thing so it never raises (return the empty shape on failure).

- [ ] **Step 4: Run service test → pass.**

- [ ] **Step 5: Add the page test, view, url, template**

Test (`web/tests/test_pages.py`, service mocked):

```python
class ClassicsPageTests(TestCase):
    @mock.patch("web.views.get_classic_movie_night",
                return_value={"next_screening": None, "upcoming": []})
    def test_empty_state(self, _m):
        html = self.client.get(reverse("classics")).content.decode()
        self.assertIn("CLASSIC MOVIE NIGHT", html)
        self.assertIn("classic-movie-page__empty", html)   # film-reel empty state

    @mock.patch("web.views.get_classic_movie_night")
    def test_next_screening(self, m):
        m.return_value = {"next_screening": {"id": "1", "title": "Casablanca",
            "poster": "c.jpg", "rating": "PG", "runtime": "1h 42min",
            "synopsis": "A classic.", "youtube_id": "z", "date": "2999-03-01",
            "display_date": "Friday, March 1"}, "upcoming": []}
        html = self.client.get(reverse("classics")).content.decode()
        self.assertIn("Casablanca", html)
        self.assertIn("classic-movie-page__featured", html)
```

View + url:

```python
from web.services.leprinceos import (get_now_showing, get_coming_soon,
                                      get_classic_movie_night)

class ClassicsView(TemplateView):
    template_name = "web/classics.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["classics"] = get_classic_movie_night()
        return ctx
```
`web/urls.py`: `path("classics/", ClassicsView.as_view(), name="classics"),`

Template `web/templates/web/classics.html` — transcribe `ClassicMoviePage.jsx` preserving classes. Interactivity mapping:
- Wrap the screenings area in Alpine `x-data="{ expanded: null }"`.
- **Empty state**: render `classic-movie-page__empty` (with the film-reel SVG verbatim) when `not classics.next_screening and not classics.upcoming`.
- **Next screening**: the `classic-movie-page__featured` button toggles `expanded` to a key like `'{{ classics.next_screening.id }}-next'`; `:class` adds `--expanded` when active; the expanded details (`classic-movie-page__expanded` with synopsis + inline trailer iframe — NO autoplay) render with `x-show="expanded === '...-next'"`.
- **Upcoming grid**: each card button toggles `expanded` to `'{{ movie.id }}-{{ movie.date }}'`; the shared expanded-detail area below the grid renders the matching movie via `x-show`/`x-if` per movie (simplest: render each movie's expanded block with `x-show="expanded === '<key>'"`).
- Trailer iframe uses `youtube-nocookie.com/embed/{{ youtube_id }}?modestbranding=1&rel=0&showinfo=0&iv_load_policy=3` (no autoplay).
- Membership CTA at the bottom (`classic-movie-page__cta`) → `<a href="/membership">`.
- Link `ClassicMoviePage.css`. No loading state needed (server-rendered).

- [ ] **Step 6: Run → pass**, then full suite.

- [ ] **Step 7: Commit**

```bash
git add web/services/leprinceos.py web/templates/web/classics.html web/views.py web/urls.py web/tests/test_leprinceos.py web/tests/test_pages.py
git commit -m "feat(web): /classics page + get_classic_movie_night service (Alpine expand/trailer)"
```

---

### Task 5: Coming Soon calendar view (`get_calendar_month` + HTMX month nav)

Completes the Coming Soon section (Plan 2 shipped grid-only): adds the grid↔calendar view toggle (Alpine) and the calendar view whose month grid + prev/next navigation load via HTMX from a new `/calendar/<year>/<month>` fragment endpoint, backed by a new `get_calendar_month()` service.

**Files:**
- Modify: `web/services/leprinceos.py` (add `get_calendar_month(year, month)`), `web/views.py` (add `CalendarMonthView`), `web/urls.py` (calendar route), `templates/partials/coming_soon.html` (add toggle + calendar container), `web/tests/test_leprinceos.py`, `web/tests/test_pages.py`
- Create: `templates/partials/calendar_month.html`
- Reference: SPA `src/services/api.js` (`getCalendarMonth`), `src/components/ComingSoon/ComingSoon.jsx` (the `viewMode==='calendar'` branch + `coming-view-toggle`)

**Interfaces:**
- Produces:
  - `get_calendar_month(year, month) -> dict` — `{ <day:int>: [ {"id": str, "title": str, "poster": str, "youtube_id": str}, ... ] }` (movies grouped by local day; `month` is 0-based to match the SPA/JS, OR document 1-based — pick **0-based** to match `api.js` and the view will pass it through). Cached/guarded.
  - URL name `calendar_month` at `calendar/<int:year>/<int:month>/`; `CalendarMonthView` renders `partials/calendar_month.html` (fragment) with `year`, `month`, the day cells, and the month label + prev/next targets.
  - `partials/calendar_month.html` — the month nav (label + prev/next `hx-get` buttons targeting itself via `outerHTML`) + the day-of-week headers + the calendar cells (empties for leading blanks, days with movie posters).

- [ ] **Step 1: Write the failing service test**

Add to `web/tests/test_leprinceos.py`:

```python
class GetCalendarMonthTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_groups_movies_by_local_day(self):
        showtimes = [
            {"id": 300, "starts_at": "2999-05-04T23:00:00Z",  # May 4 EDT
             "film_title": "Wicked", "film_poster_url": "w.jpg", "youtube_id": "y"},
        ]
        with mock.patch("web.services.leprinceos.requests.get",
                        return_value=_resp({"results": showtimes})):
            data = leprinceos.get_calendar_month(2999, 4)   # month 4 == May (0-based)
        self.assertIn(4, data)                              # day 4
        self.assertEqual(data[4][0]["title"], "Wicked")
        self.assertEqual(data[4][0]["poster"], "w.jpg")

    def test_empty_month(self):
        with mock.patch("web.services.leprinceos.requests.get",
                        return_value=_resp({"results": []})):
            self.assertEqual(leprinceos.get_calendar_month(2999, 4), {})
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `get_calendar_month(year, month)`**

Port `getCalendarMonth` from `api.js` (month is 0-based). Build the month's UTC-ish date range in `CINEMA_TZ`, fetch `/showtimes/?is_cancelled=false&starts_at_after=<start>&starts_at_before=<end>`, group by local day (`_local_date` → day int), dedup movies per day by title, output `{day: [{"id","title","poster","youtube_id"}]}`. Guard per-record + overall (return `{}` on failure).

- [ ] **Step 4: Run service test → pass.**

- [ ] **Step 5: Add the fragment view + url + template**

`CalendarMonthView` (a plain `View` or `TemplateView`) rendering `partials/calendar_month.html`. In `get_context_data`/`get`, compute from `year`+`month` (0-based): the `calendar_data = get_calendar_month(year, month)`; the `month_label` (`date(year, month+1, 1).strftime("%B %Y").upper()`); `first_weekday` (`date(year, month+1, 1).weekday()` adjusted so **Sunday=0** to match the SPA's `getDay()`), `days_in_month`; and the prev/next `(year, month)` pairs (wrapping December→January). Pass a `cells` list: leading `None`s for blanks then day ints, each day annotated with its movies from `calendar_data`.

`web/urls.py`: `path("calendar/<int:year>/<int:month>/", CalendarMonthView.as_view(), name="calendar_month"),`

`templates/partials/calendar_month.html` — transcribe the `viewMode==='calendar'` branch of `ComingSoon.jsx` preserving classes (`coming-calendar`, `coming-calendar-nav`, `coming-calendar-nav__arrow`, `coming-calendar-nav__label`, `coming-calendar-grid`, `coming-calendar-dayheader(--full/--short)`, `coming-calendar-cell(--empty/--has-movie)`, `coming-calendar-cell__day/__movies/__poster(--playable)/__img/__placeholder`). The nav arrows are HTMX:

```django
<button class="coming-calendar-nav__arrow" aria-label="Previous month"
        hx-get="{% url 'calendar_month' prev_year prev_month %}"
        hx-target="closest .coming-calendar" hx-swap="outerHTML">&#8249;</button>
```

(and similarly for next). Wrap the whole fragment in the `coming-calendar` element so `hx-target="closest .coming-calendar"` + `outerHTML` swaps the entire month. Day-cell posters that have `youtube_id` open the ComingSoon trailer modal — but that modal's Alpine state lives on the parent section; the calendar cells can dispatch to it via `@click="$dispatch(...)"` OR, to keep Task 5 self-contained, render the calendar poster as a non-interactive image in the calendar view (the SPA opened the trailer; if wiring the modal across the HTMX boundary is awkward, render the poster with its `title` tooltip and no click — note this as a minor deviation). Prefer wiring it if straightforward via an Alpine store; otherwise the non-interactive fallback is acceptable and documented.

- [ ] **Step 6: Wire the toggle into `coming_soon.html`**

In `templates/partials/coming_soon.html`: add the `coming-view-toggle` (the two grid/calendar buttons from `ComingSoon.jsx`) into the section header, and add Alpine `view` state to the section's `x-data` (extend the existing `{ trailer: null }` to `{ trailer: null, view: 'grid' }`). Grid wrapper gets `x-show="view === 'grid'"`; add a calendar container `x-show="view === 'calendar'"` that lazy-loads the initial month via HTMX on first reveal:

```django
<div class="coming-calendar-container" x-show="view === 'calendar'"
     hx-get="{% url 'calendar_month' initial_year initial_month %}"
     hx-trigger="intersect once" hx-swap="innerHTML"></div>
```

The toggle buttons set `view` and get `coming-view-btn--active` via `:class`. Compute `initial_year`/`initial_month` (0-based) in `HomeView.get_context_data` from the earliest `coming_soon` `start_date` (else the current Eastern month) and pass them through (the calendar container is part of the home page's ComingSoon include).

- [ ] **Step 7: Page test**

Add a test that the calendar fragment endpoint returns 200 + the calendar markup (service mocked), and that the home ComingSoon renders the view-toggle:

```python
class CalendarTests(TestCase):
    @mock.patch("web.views.get_calendar_month", return_value={})
    def test_calendar_fragment_200(self, _m):
        resp = self.client.get(reverse("calendar_month", args=[2999, 4]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "partials/calendar_month.html")
        self.assertIn("coming-calendar", resp.content.decode())

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_home_has_view_toggle(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("coming-view-toggle", html)
```

- [ ] **Step 8: Run → pass**, then full suite.

- [ ] **Step 9: Commit**

```bash
git add web/services/leprinceos.py web/templates web/views.py web/urls.py templates/partials/coming_soon.html templates/partials/calendar_month.html web/tests/
git commit -m "feat(web): Coming Soon calendar view + get_calendar_month + HTMX month nav"
```

---

## Self-Review

**Spec coverage (design doc build order items 4):**
- `/membership`, `/rentals`, `/about`, `/classics` pages → Tasks 1–4. Classics service (`get_classic_movie_night`) → Task 4. ComingSoon calendar view toggle + month HTMX nav (deferred from Plan 2) → Task 5 (`get_calendar_month`).
- After this plan, every `site_config.navigation` link resolves; the Plan 3 nav's non-home hash-link branch is now exercised by these routes.
- **Deferred (Plan 5):** sitemap/robots, JSON-LD polish, full Selenium E2E, deployment cutover; the site-wide default `og:image` root-path + canonical query-string cleanup.

**Placeholder scan:** No TBDs. The one conditional ("wire the calendar poster→trailer modal across the HTMX boundary, else non-interactive fallback") is an explicit, bounded decision with a documented acceptable fallback, not hand-waving. The Rentals/About tasks say "transcribe the WHOLE file" — the source files are the complete, unambiguous spec for those verbatim static ports (their length makes inlining them here counterproductive and drift-prone).

**Type/name consistency:** service outputs are snake_case (`next_screening`, `display_date`, `youtube_id`); view context keys (`tiers`, `faqs`, `classics`, `initial_year`, `initial_month`) match templates and tests. URL names (`membership`, `rentals`, `about`, `classics`, `calendar_month`) are consistent across `web/urls.py`, templates, and tests. The calendar `month` is 0-based end-to-end (service, view, url, `api.js` parity). `data-spotlight`/`data-reveal` hooks match the effects scanners. Views import the service fetchers into `web.views` so tests mock at `web.views.<name>` (consistent with Plan 2's pattern).
