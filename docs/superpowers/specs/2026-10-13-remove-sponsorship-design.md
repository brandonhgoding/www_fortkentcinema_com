# Remove sponsorship — design

Date: 2026-10-13
Status: approved in conversation; awaiting review of this written spec

## Goal

Remove film sponsorship from the site completely: the public `/sponsor/`
page, sponsorship inquiries (model, dashboard, alert), the studio film
catalog that fed the page, the sponsored-screening banner, and the home
page's Support strip. Rentals must keep working exactly as it does today.

## Decisions (the owner's)

| Question | Decision |
|---|---|
| Scope | Everything sponsorship, including the Studio/StudioTitle catalog and the sponsored-screening banner |
| Existing rows in production | Drop them. No export |
| Support strip (off today) | Remove it entirely, donate card included |
| Old `/sponsor/` URL | Plain 404, like `/craft-night/` |
| Delivery | One branch, one deploy, a new migration that drops the tables |

## Assumptions

- Anything used only by sponsorship goes too: `render_promo_cards` and
  `cinema/social_cards/promo.py` (their only output is `og-sponsor.jpg`),
  the `DONATION` constant (used only by the donate card), and the catalog
  import helpers.
- Historic migrations stay. `0010_screen_capacity_backfill` depends on
  `0009_sponsorshipinquiry`, and neither 0008 nor 0009 imports model code.
- Planning docs under `docs/` are history and stay.
- The "Advertise with us" home card is unrelated and untouched.

## Section 1 — Protect rentals first

Two pieces of rentals currently live in sponsorship code. They move before
anything is deleted.

1. **`InquiryStatus`** (NEW / CONTACTED / WON / LOST) is defined in
   `cinema/models/sponsorship_inquiry.py` and imported by
   `cinema/models/rental_inquiry.py`, `dashboard/rental_inquiry_views.py`,
   `dashboard/views.py` and tests. Move it into `rental_inquiry.py` with the
   same name and values, and export it from `cinema/models/__init__.py`.
   No database change: migration `0019_rental_inquiry` has its own inline
   choices.
2. **Rental form styles.** `templates/partials/rental_inquiry_form.html`
   uses `.sponsor-inquire__form`, `__field`, `__label`, `__error`,
   `__field-error` and `__sent`, defined in `static/css/SponsorPage.css`
   (~lines 593–740), with `PrivateRentalsPage.css` building on them. Move
   those rules into `PrivateRentalsPage.css` under rental class names
   (`.rental-inquire__…`) and update the template. The form must render
   pixel-identically.

Known side effect: `/rentals/` loses its only internal inbound link (the
`/sponsor/` FAQ). It stays in the sitemap and `llms.txt`, and it is already
on the owner's "needs a home" list.

## Section 2 — What gets removed

### Public site

- URLs `sponsor/`, `sponsor/inquire`, `sponsor/catalog`, `sponsor/films`
  (`web/urls.py`).
- Views in `web/views.py`: `SPONSOR_SORTS`, `SponsorCatalogMixin`,
  `SponsorView`, `SponsorCatalogView`, `SponsorFilmOptionsView`,
  `SponsorInquiryView`, `sponsored_screening()`, and the `HomeView`
  context keys `sponsored`, `show_support`, `sponsorship_from_price`,
  plus the donate URL key, and `LlmsTxtView`'s `sponsor_from`.
- `SponsorshipInquiryForm` (`web/forms.py`) and its `StudioTitle` import.
- Templates: `web/templates/web/sponsor.html`;
  `templates/partials/sponsor_catalog.html`, `sponsor_film_options.html`,
  `sponsor_inquiry_form.html`, `cta_sponsor.html`, `cta_sponsored.html`,
  `home_support.html`, `cta_donate.html`.
- Includes: `cta_sponsored.html` from `now_showing.html`;
  `home_support.html` from `web/templates/web/home.html`, whose composition
  comment drops the `support` row and the sponsored-banner mentions.
- CSS: `static/css/SponsorPage.css` and `static/css/SponsoredCTA.css`
  (after Section 1), their `@import`s in `frontend/styles/main.css`, and
  the Support strip's rules in `static/css/HomeSections.css`. Comment-only mentions
  elsewhere are reworded where they would point at something deleted.
- `static/img/og-sponsor.jpg`.
- Sitemap: the `sponsor` lastmod and item (`web/sitemaps.py`).
- `templates/llms.txt`: the sponsor line. The heading "Rentals,
  sponsorship, gift cards" becomes "Rentals, gift cards".
- Coming Soon's empty state: the "Pick a film and sponsor it" item
  (`templates/partials/coming_soon.html`).

### Constants (`web/constants.py`)

`SPONSORED_SCREENING`, `SPONSORSHIP_POPCORN_CAP`, `SPONSORSHIP_SHOWCASE`,
`SPONSORSHIP_TIERS`, `SPONSORSHIP_TIER_LABELS`, `SPONSORSHIP_FAQ`,
`SHOW_SUPPORT_STRIP`, `DONATION`, and the comments that describe them or
point at `/sponsor/`.

### Dashboard

- `dashboard/inquiry_views.py`, the `inquiries` and
  `inquiries/<pk>/status` routes, and `dashboard/templates/dashboard/inquiries.html`.
- The sidebar "Inquiries" entry. "Rental Inquiries" stays.
- The `new_inquiries` argument and the `new-sponsorship-inquiries` alert in
  `dashboard/smart_alerts.py`, and the count passed from `dashboard/views.py`.
  The rental and voicemail alerts are unchanged.

### Admin and management commands

- `cinema/admin.py`: `StudioAdmin`, `StudioTitleAdmin` (with its custom
  "Import catalog" URL and view), `SponsorshipInquiryAdmin`.
- `templates/admin/cinema/studiotitle/change_list.html` and
  `import_catalog.html`.
- `cinema/management/commands/import_studio_catalog.py`,
  `cinema/studio_import.py`, `cinema/studio_catalog.py`, and
  `cinema/forms.py` (its only class is `StudioCatalogImportForm`).
- `cinema/management/commands/render_promo_cards.py` and
  `cinema/social_cards/promo.py`. Nothing else imports `promo.py`; the
  rest of `cinema/social_cards/` (film and blog cards) stays.

### Models

`cinema/models/sponsorship_inquiry.py`, `studio.py`, `studio_title.py` and
their exports in `cinema/models/__init__.py`.

### Tests

- Deleted: `web/tests/test_sponsor.py`, `test_sponsor_inquiry.py`,
  `test_sponsor_seo.py`, `test_sponsored_screening.py`,
  `web/tests/test_donate_cta.py`, `dashboard/tests/test_inquiries.py`,
  `cinema/tests/test_studio_models.py`, `test_import_studio_catalog.py`,
  `test_studio_import.py`, `test_studio_catalog.py`,
  `test_admin_catalog_import.py`. The promo-card checks live in
  `test_sponsor_seo.py` (`SponsorSocialCardTests`) and go with it.
- Moved, not deleted: `StaticSitemapLastmodTests` in `test_sponsor_seo.py`
  guards every page's sitemap date. It moves unchanged to a new
  `web/tests/test_sitemap_lastmod.py`.
- Edited: the sponsorship parts of `web/tests/test_home_sections.py`,
  `test_home_appendix.py`, `test_llms_txt.py`, `test_nav.py`,
  `test_performance.py`, `test_rental_inquiry.py` and
  `dashboard/tests/test_smart_alerts.py`.

### Kept on purpose

The historic migrations, the screen-capacity data and
`cinema/screen_capacity.py` (its docstring is reworded so it no longer
gives sponsorship as the reason), the `docs/` history, and the Advertise
card.

## Section 3 — Database migration

- A new `cinema/migrations/0024_…` generated by `makemigrations` that
  deletes `SponsorshipInquiry`, then `StudioTitle`, then `Studio`. It must
  contain those removals only.
- `Film` loses the reverse relation `studio_titles`. Its table does not
  change.
- `RentalInquiry` does not appear in the migration.
- Deploying runs the migration, and the tables and their rows are gone.
  Rolling back would recreate empty tables only. Code and migration ship
  together.

## Section 4 — Testing and verification

- One branch, ordered commits (Section 1, then the public site, dashboard,
  admin and commands, models and migration). The full suite passes after
  each. Tests are written first.
- A new `web/tests/test_sponsorship_removed.py` asserts:
  - `/sponsor/`, `/sponsor/inquire`, `/sponsor/catalog` and
    `/sponsor/films` return 404.
  - `reverse("sponsor")` raises `NoReverseMatch`.
  - The sitemap and `llms.txt` have no sponsorship.
  - The home page has no `sponsored-cta` and no Support strip.
  - `dashboard:inquiries` no longer resolves.
- Rentals tests assert that the form renders with the `rental-inquire__`
  classes and that statuses NEW, CONTACTED, WON and LOST still save.
- `makemigrations --check` is clean after 0024, `migrate` runs clean on a
  fresh database, and 0024 migrates forwards and back on a scratch
  database.
- Before/after screenshots of the `/rentals/` form match. Screenshots of
  the home page and the dashboard home show nothing broken or empty.
- The CSS bundle is rebuilt, and the full suite is green at the end.
- Commit, merge and push only when the owner asks. The owner deploys. No
  cron or scheduled task references the removed commands.
