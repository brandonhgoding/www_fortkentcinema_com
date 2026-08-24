# Film Sponsorships — studio catalogs, `/sponsor/`, and inquiries — Design

**Date:** 2026-08-23
**Status:** Awaiting user review (design phase)
**Repo:** `api_fortkentcinema_com` (branch: new `feat/film-sponsorships`)

## Context

Local businesses can underwrite a screening: the sponsor covers the film's booking
fee in exchange for promotion, and can optionally cover admission and concessions
so the show is free to the public. A.H. Custom Carpentry is doing exactly this for
*The Wild Robot* at the end of August 2026 — that arrangement is the model this
feature productizes.

To sell it we need to show businesses what they can actually pick from. Universal
supplies a DCP availability list (`Universal DCP List - Updated 3.4.26.xlsx`,
1148 rows → 1140 titles); other studios will follow. This adds three things:

1. Studio catalog models + an idempotent importer.
2. A public `/sponsor/` page: the pitch, the tiers, and a searchable table of
   available titles.
3. An inquiry form whose submissions land in the dashboard.

Payment is explicitly **out of scope**. Inquiries start a conversation; money is
handled offline, as it is for private rentals today.

## Decisions

### Studio titles do not go in `Film`

`Film` is the *site catalog* — every row has a slug, a `/movies/<slug>` page, TMDB
enrichment, and a place in `FilmSitemap`. It holds 66 rows, 46 with engagements.
Importing 1148 Universal titles into it would grow it ~18x with films we have never
screened and cannot describe, creating 1100+ thin pages that the sponsor table
would link directly into. `FilmSitemap` already excludes never-engaged films, so
they would stay out of the sitemap, but they would still be crawlable.

Only **5 of the 1148 titles** match a `Film` we already have, so the reuse argument
is nearly worthless. Universal's data is also mostly exhibition metadata — aspect
ratio, audio formats, DCP notes — that `Film` has nowhere to put.

New models `Studio` and `StudioTitle` live in `cinema`, with a **nullable** FK from
`StudioTitle` to `Film` for the handful that overlap. `Film` keeps meaning
"films we have actually shown."

### Availability is opt-out

Everything Universal lists is sponsorable by default (`is_available=True`). Titles
are hidden case by case with a recorded `hidden_reason`. Opt-in curation would
leave the page empty until 1148 rows were reviewed by hand.

There is no "claimed" state. Sponsorships are tracked in conversation, not in the
app; adding claim tracking before a single inquiry exists is speculative.

### Duplicate titles are DCP variants, not duplicates

Six titles repeat across nine extra rows. Only *Notting Hill* is a true duplicate.
The rest are genuinely distinct bookable inventory:

| Title | Variants |
|---|---|
| Touch of Evil | 1958 theatrical (95 min, unrated) / 1998 reconstruction (110 min, PG-13) |
| Dracula (1931) | original mono / 5.1 rescore; also two release dates (Feb 13, Apr 24) |
| It Came From Outer Space | 2D / 3D |
| The Man Who Laughs | MOS / mono / 3.0 |
| Sweet Charity | roadshow at 151 / 148 / 145 min |

Blind de-duplication would discard real inventory. The importer collapses on the
natural key and preserves what it collapsed in `variant_note` (see below).

Collapsing 1148 sheet rows on `(title, release_date)` yields **1140 `StudioTitle`
rows** across 6 multi-row groups. Note the consequence: *Dracula* has two distinct
release dates (1931-02-13 and 1931-04-24), so it survives as **two rows** and will
appear twice in the public table. That is accurate — they are two different
bookable presentations — but it is a deliberate outcome, not a bug to fix later.

### The table is server-side

`/sponsor/` filters, sorts, and paginates in Django via querystring. Client-side
filtering would be snappier at 1148 rows, but the catalog grows with every studio
added, and server-side is the shape that survives 5000 titles without a rewrite.

### Inquiries do not send email

Nothing in this project sends mail — there is no `EMAIL_*` setting, and
`VoteSubscribeView` documents that the subscriber list is exported and mailed by
hand. Rather than add an email backend and another pending production deploy step,
inquiries are stored and surfaced two ways: a dashboard list view, and a line in
the existing `build_smart_alerts` strip on the dashboard home. Email notification
is a reasonable follow-up, not part of this work.

## Architecture

### `cinema/models/studio.py`

```python
class Studio(models.Model):
    name = models.CharField(max_length=100, unique=True)   # "Universal Pictures"
    slug = models.SlugField(max_length=100, unique=True)   # "universal"
    is_active = models.BooleanField(default=True)
    catalog_updated = models.DateField(null=True, blank=True)  # list's own revision date
```

`is_active=False` pulls a whole studio's catalog off the page at once (rights
lapse, list goes stale) without touching per-title flags.

### `cinema/models/studio_title.py`

```python
class StudioTitle(models.Model):
    studio           = FK(Studio, related_name="titles", on_delete=CASCADE)
    original_title   = CharField(200)        # "BAD GUYS 2, THE" — verbatim, for re-import matching
    title            = CharField(200)        # "The Bad Guys 2" — normalized, for display
    release_date     = DateField(null=True, blank=True)
    aspect_ratio     = CharField(60, blank=True)
    audio            = CharField(60, blank=True)
    mpa_rating       = CharField(20, blank=True)
    runtime_minutes  = PositiveIntegerField(null=True, blank=True)   # parsed, for sort/display
    runtime_raw      = CharField(60, blank=True)                     # "119 & 146" preserved
    notes            = CharField(200, blank=True)                    # ADDITIONAL INFORMATION
    variant_note     = CharField(300, blank=True)                    # collapsed variants
    film             = FK(Film, null=True, blank=True, on_delete=SET_NULL,
                          related_name="studio_titles")
    is_available     = BooleanField(default=True)
    hidden_reason    = CharField(200, blank=True)
    imported_at      = DateTimeField(auto_now_add=True)
    updated_at       = DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("studio", "original_title", "release_date")
        ordering = ["title"]
        indexes = [Index(fields=["studio", "is_available"]),
                   Index(fields=["title"])]
```

`release_year` is a property off `release_date` (one row has no date). The public
queryset is `StudioTitle.objects.filter(is_available=True, studio__is_active=True)`,
exposed as a manager method `available()`.

**Display format string** — a `format_summary` property joining the non-empty parts
of `aspect_ratio`, `audio`, `notes` with `·` (e.g. "Scope · 5.1, 7.1, Atmos · 4K").
Exhibition trivia to a business owner, but worth one quiet column.

### Title normalization

`cinema/studio_catalog.py` holds two pure functions, unit-tested independently of
the importer:

`normalize_title(raw)`:
1. Split off a trailing parenthetical (`SCARFACE (1932)`, `2 FAST 2 FURIOUS (aka …)`).
2. If the remainder ends `, THE` / `, A` / `, AN`, move that article to the front.
3. Title-case on word boundaries that **do not** split at apostrophes — `.title()`
   would produce `Freddy'S`. Keep small words (`of a an the and or in on at to for
   from with vs`) lowercase unless first or last.
4. Reattach the parenthetical, left untouched if it already contains lowercase
   (the `aka …` suffixes are already correctly cased).

`parse_runtime(value)` → `(minutes:int|None, raw:str)`. Ints pass through. Strings
match `^\s*(\d+)` to take the leading number — covering `119 & 146`,
`94\n(incl 5min short)`, and `91 (inc. 4 min. short)` — and the original string is
always preserved in `runtime_raw`.

### `cinema/management/commands/import_studio_catalog.py`

```
python manage.py import_studio_catalog --studio universal \
    --file "Universal DCP List - Updated 3.4.26.xlsx" [--sheet "by TITLE"] [--dry-run]
```

Modeled on `backfill_past_films.py`: module docstring explaining intent, `--dry-run`
first, safe to re-run on prod.

- `get_or_create` the `Studio` from `--studio` (slug → known display names).
- Read the `by TITLE` sheet. The two sheets carry identical content (verified: the
  title sets match exactly); `--sheet` exists to override if a future list differs.
- Group rows by the natural key `(original_title, release_date)`. Within a group,
  the **primary** row is the one with the longest parsed runtime; ties break on most
  non-empty fields, then on sheet order (first wins) so the result is deterministic
  — both *Dracula* 1931-02-13 rows are 75 min and differ only in audio, so without
  that final tie-break the import would not be reproducible. Every other row in the
  group is summarized into `variant_note`
  — e.g. *"Also available: 4K Restoration (Original 1958 Theatrical Version), 95
  min, unrated"* — so nothing is silently dropped.
- `update_or_create` on the natural key. **`is_available` and `hidden_reason` are
  never overwritten on update** — a re-import must not resurrect a title you hid.
- Report created / updated / unchanged / variants-collapsed / skipped counts.

Idempotent: running it twice changes nothing the second time.

Invocation:

```bash
.venv/bin/python manage.py import_studio_catalog \
  --studio universal \
  --file "/Users/bgoding/Documents/Universal DCP List - Updated 3.4.26.xlsx" \
  --dry-run
```

**Dependency gap:** `openpyxl` (3.1.5) is present in the local venv but is **not
declared in `requirements.txt`** — nothing in the project currently imports it. It
must be added, or the command dies with `ModuleNotFoundError` on a fresh checkout
and in production. This is the first real dependency the repo has needed since the
initial pin set, so it goes in `requirements.txt` under a new `# Spreadsheet import`
heading rather than into `dev-requirements.txt`: the importer is a production
management command, not a dev tool.

### `web/constants.py`

Sponsorship tiers live beside `MEMBERSHIP`, following the same list-of-dicts shape
the membership page already loops over.

```python
SPONSORSHIP_POPCORN_CAP = 100     # matches a full house; see Screen.capacity below
SPONSORSHIP_TIERS = [
    {
        "key": "presenting",
        "name": "Presenting Sponsor",
        "price": 299,
        "eyebrow": "Cover the film",
        "includes": [
            "We book the title you pick",
            "Social media plugs in the run-up to the show",
            "Your name on the marquee",
            "Preshow credit slide on screen",
        ],
    },
    {
        "key": "community",
        "name": "Community Screening",
        "price": 499,
        "eyebrow": "Cover the film + admission",
        "includes": [ ...presenting..., "Admission is free to the public" ],
    },
    {
        "key": "full_house",
        "name": "Full House",
        "price": 799,
        "eyebrow": "Cover the film, admission + popcorn",
        "includes": [ ...community...,
                      "Medium buttered popcorn for the first 100 guests" ],
    },
]
```

Each tier's `includes` list is written out in full in the constant (spelled
`...presenting...` here only to keep the spec readable) — the template renders the
list verbatim rather than composing tiers from each other, matching how
`MEMBERSHIP` repeats its shared perks per tier.

**Pricing rationale** (recorded so the numbers can be revisited deliberately):

| Tier | Price | Basis |
|---|---|---|
| Presenting Sponsor | $299 | Universal's flat $200 booking fee + $99 toward staff, projection, and promotion |
| Community Screening | $499 | + free public admission. At ~6 admissions/showtime baseline (FY2026), a free promoted screening fills a near-empty room rather than cannibalizing ticket sales |
| Full House | $799 | + medium buttered popcorn for the first 100 guests. Retail would be $625 (100 × $6.25), but at a 30–50% concession attach rate the real cost is ~$250 forgone revenue + ~$60 materials ≈ $300 |

Tier 3 copy must state both the **100-guest cap** and **medium, butter included**,
so there is no argument at the counter.

### `/sponsor/` — `web/views.py`

`SponsorView(ListView)`, `paginate_by = 50`, template `web/templates/web/sponsor.html`.

Querystring: `?q=` (title contains), `?rating=`, `?decade=`, `?sort=`, `?page=`.
`sort` is validated against an allowlist (`title`, `-title`, `year`, `-year`,
`runtime`, `-runtime`) and falls back to `title` — never interpolated into
`order_by` unchecked. Rating and decade choices are derived from the available
queryset so they never offer an empty filter. Sortable column headers are plain
links that preserve the other params.

Page structure: hero → the A.H. Custom Carpentry / *The Wild Robot* example as a
worked case study → three tier cards → the searchable table → inquiry form.

URL `path("sponsor/", …, name="sponsor")`, matching the trailing-slash convention of
`/membership/` and `/rentals/`. Added to `StaticViewSitemap.items()`. Linked from
`templates/partials/footer.html`.

### Inquiries

```python
class SponsorshipInquiry(models.Model):
    business_name, contact_name, email, phone(blank), message(blank)
    studio_title = FK(StudioTitle, null=True, blank=True, on_delete=SET_NULL)
    tier         = CharField(choices from SPONSORSHIP_TIERS keys, blank=True)
    status       = CharField(choices=InquiryStatus, default=NEW)  # NEW/CONTACTED/WON/LOST
    created_at, ip
```

`SponsorInquiryView(View)` handles `POST /sponsor/inquire` (no trailing slash,
matching `/vote/cast`). Honeypot `website` field short-circuits to the success state
exactly as `VoteSubscribeView` does. Validation errors re-render the form with the
submitted values preserved. The title field is optional — a business may want to
sponsor *something* without having picked a film yet.

Dashboard: `dashboard/inquiry_views.py` alongside `subscriber_views.py`, list view
with status filter and a status-change action. `build_smart_alerts` gains a
`NEW`-count alert — *"You have 3 new sponsorship inquiries"* — in the same shape as
the existing draft-engagements alert.

### `Screen.capacity` data fix

Both `Screen` rows (`The Century`, `The Savoy`) have `capacity = 1`, which is
placeholder data and makes any house-size reasoning nonsense. A data migration sets
`capacity = 100` **only where `capacity <= 1`**, so it cannot clobber real values if
production already has them. The real seat counts are to be measured later; 100 is
the working figure and is what the tier-3 popcorn cap is aligned to.

## Testing

TDD throughout. The gates that actually run in this project are `flake8` and
`python manage.py test` (mypy does not run here).

- `cinema/tests/test_studio_catalog.py` — `normalize_title` against the real
  awkward cases (`BAD GUYS 2, THE`, `FIVE NIGHTS AT FREDDY'S 2`, `SCARFACE (1932)`,
  `2 FAST 2 FURIOUS (aka Fast & Furious 2)`); `parse_runtime` against all ten
  non-integer values in the sheet.
- `cinema/tests/test_import_studio_catalog.py` — fixture workbook: creates rows,
  is idempotent on re-run, collapses the Touch of Evil / Sweet Charity variants into
  `variant_note`, preserves `is_available=False` across a re-import, handles the
  one null release date, `--dry-run` writes nothing.
- `web/tests/test_sponsor.py` — page renders; `q`/`rating`/`decade` filter; sort
  allowlist rejects injection; pagination; hidden and inactive-studio titles never
  appear; sitemap includes `sponsor`.
- `web/tests/test_sponsor_inquiry.py` — valid POST creates a row, invalid POST
  re-renders with errors and values intact, honeypot silently succeeds without
  creating a row.
- `dashboard/tests/` — inquiry list renders and filters; smart alert appears at
  count ≥ 1 and is absent at 0.

## Out of scope

Payment/checkout, email notification, sponsor logo uploads, claim/booking state on
titles, and studios beyond Universal. The importer is `--studio`-parameterized so
the next studio is a data task, not a code change.
