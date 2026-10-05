# Square Sync — ticket items pushed, sales pulled — Design

**Date:** 2026-10-05
**Status:** Implemented on feat/square-sync (see Amendments)
**Repo:** `www_fortkentcinema_com` (branch: new `feat/square-sync`)

## Context

Square is the register and the money. Django is the schedule and the website.
Today nothing connects them, and the seam shows in both directions.

**Going in.** Every run gets a ticket item typed into Square by hand, a second
time after it was entered in the dashboard. The live catalog (read 2026-10-05)
has a misspelled title ("Varity"), two ticket items with no category at all,
and per-showtime items spread across three categories (Movies, Events,
Pre-Sales). The nightly report filters on one category ID, so the stray items
are invisible to it.

**Coming out.** A standalone script (`../flashGrossesScript`) pulls the day's
Square orders, sums line items, and emails an owner summary plus a ticket-only
report. It works, but it lives outside this project with its own `.env`, its
own SMTP code, and no record of what it sent. `Engagement.admissions` is a
hand-typed field whose help text already says "from Square sales data".

This spec puts both halves inside Django:

1. **Push.** A confirmed engagement produces its Square ticket item in the
   Movies category, with the five priced tiers as variations. Django stores
   the Square IDs. Edits re-push; a finished run's item is deleted.
2. **Pull.** A nightly management command fetches the business day's orders,
   stores every line item, attributes ticket sales to engagements by the IDs
   Django issued, recomputes admissions, and sends the two existing reports
   to admin-managed recipients.

Square stays the system of record for money. Django stays the system of record
for what is playing. Neither side guesses at the other's data.

### Explicitly out of scope

- **Per-showtime ticket items.** The live catalog has items with one
  variation per showtime at a flat price (events, pre-sales). This project
  does not build that shape. Every engagement gets the same five tiered
  variations. If per-show counts are wanted later, that is a new spec.
- **Webhooks.** No real-time push from Square. The only real-time need
  identified is verifying membership payments on `/thanks`, and that is a
  one-event webhook for a later spec. Everything here is nightly or on-save.
- **Concessions, apartments, gift cards, donations.** Square owns these items.
  Django never creates, edits, or deletes an item it did not create.
- **Membership items and payment links.** Designed below as **Phase 2** so
  the data model does not paint it out, but not built in this pass. Tickets
  are the live problem.
- **Refunds.** Sales are summed from completed orders; a refund the next day
  is not subtracted. The old script had the same behaviour. A later addition
  once there is a sales table to subtract from.
- **Backfilling past runs.** Items made by hand before cutover are not linked.
  Pre-cutover `admissions` values stay as typed. Same call as the membership
  term backfill: no importer for a one-time job.
- **Rich reporting.** The dashboard gets a status pill, one sales panel, and
  two alerts. Per-run gross, concessions per head, and week-over-week views
  are a later spec that reads the table this one creates.

## Decisions

### A new app, `boxoffice`

The integration spans `cinema` (tickets), `audience` (memberships, Phase 2),
and reporting that belongs to neither. It gets its own app: the Square
gateway, the link tables, the sales ledger, the email report settings, the
management commands.

The obvious name, `square`, is ruled out: the Square SDK installs as the
top-level package `square`, and a Django app of that name would shadow it.
`boxoffice` is what the app is about — what sold at the window — and sits
beside `audience`, `cinema`, and `phone` in the same vocabulary.

`cinema` does not import `boxoffice`. The dashboard views call into
`boxoffice.sync` after their transactions commit; the engagement model stays
ignorant of Square beyond one new field that describes the run, not the
integration.

### The official SDK, pinned

`squareup` (the script pins `42.1.0.20250521`) handles auth, pagination,
retries on 429, and typed responses. It pulls in `httpx` and `pydantic`.
Writing against the REST API with `requests` would save two dependencies and
cost pagination, idempotency plumbing, and every future API change. Not worth
it.

All SDK calls go through one module, `boxoffice/gateway.py`, exposing a small
protocol: `upsert_items`, `delete_items`, `retrieve_item`, `search_orders`,
`list_catalog_items`. Tests use a fake implementing the same protocol, as
`cinema/tests/test_services.py` does for TMDB. Nothing else imports `square`.

### Sync is disabled without a token, and fails closed

```python
# settings.py
SQUARE_ACCESS_TOKEN = config("SQUARE_ACCESS_TOKEN", default="")
SQUARE_LOCATION_ID = config("SQUARE_LOCATION_ID", default="")
SQUARE_TICKET_CATEGORY_ID = config("SQUARE_TICKET_CATEGORY_ID", default="")
SQUARE_ENVIRONMENT = config("SQUARE_ENVIRONMENT", default="sandbox")
```

With an empty token, every sync entry point logs once and returns without
calling out. Dashboard saves succeed exactly as they do today. This mirrors
`TWILIO_AUTH_TOKEN`: a missing variable disables the feature, it never half
works. Local development runs against the Square sandbox, which has its own
token, location, and category IDs.

### Django only touches items it made

The rule that makes sharing one catalog safe. Django identifies its items by
the Square IDs it stored and by the SKU it wrote on every variation. It never
deletes, renames, or recategorises an item it has no link row for. The nightly
reconcile reports unknown items in the ticket category; it does not remove
them. A bug in this app can cost a bad week of ticket items. It cannot empty
the register.

### Push happens on dashboard saves, with a nightly reconcile behind it

Three views change what an item should look like: `EngagementCreateView`,
`EngagementEditView`, and `EngagementStatusView` in `dashboard/views.py`.
Each calls `boxoffice.sync.schedule(engagement)` inside its existing
`transaction.atomic()` block; `schedule` registers `transaction.on_commit(...)`,
so Square is called only after the row is really saved, and never inside the
transaction. Showtime views do not call the sync: the item does not depend on
showtimes.

A failed push does not fail the save. The link row records the error, the
toast says "Saved. Square sync failed — see the run", and the engagement page
shows a red pill with a Retry button. The nightly `sync_square_catalog`
command re-pushes anything whose stored state differs from what the engagement
now implies, and deletes items for runs that have ended. Any edit made in the
Django admin, which is not hooked, is caught there too.

Signals were considered and rejected. `post_save` cannot see the surrounding
transaction cleanly and would make the engagement model's save path depend on
network state. The explicit call in three views is more code and far easier
to read.

### What gets an item, and when

| Engagement state | Square item |
|---|---|
| `DRAFT` | none |
| `CONFIRMED`, today ≤ `end_date` | exists, kept in step |
| `CONFIRMED`, today > `end_date` | deleted by the nightly reconcile |
| `CANCELLED` | deleted |

The engagement has no `ENDED` status; a run is "ended" when today >
`end_date`, which the `CONFIRMED` rows above cover.

Items are created on confirmation regardless of `start_date`. A December
tentpole confirmed in September gets its item in September; that is what the
Pre-Sales category was for, and advance sales are the whole point.

Deletion is safe for reporting: Square orders keep each line item's name,
variation name, and catalog ID after the catalog object is gone, and
`boxoffice` has already stored the mapping. The register stays uncluttered.

### One ticket shape: five priced tiers

Every item gets one variation per entry in `web.constants.TICKET_PRICES`
that is a price, in that order, as ordinals 0–4:

| Tier | Price | SKU |
|---|---|---|
| Adult | $8 | `fkc-eng-<id>-adult` |
| Senior | $7 | `fkc-eng-<id>-senior` |
| Child | $6 | `fkc-eng-<id>-child` |
| Matinee | $6 | `fkc-eng-<id>-matinee` |
| Member | $4 | `fkc-eng-<id>-member` |

Prices are read from the constant at push time, so a reprice is the existing
one-line edit plus a reconcile run. **Adding a priced tier is a new entry in
`TICKET_PRICES` and nothing else**: the push, the SKUs, the reports, and the
tests all iterate the constant.

**Matinee is a priced variation, not a discount.** Today a matinee is rung
by applying a discount to another tier, or as Child since both are $6. A
Matinee line on the item makes the daytime/evening split visible in sales for
the first time.

**Senior members pay $4.** They ring as Member. There is no separate
senior-member tier.

**Free-for-members runs get no $0 variation.** A run marked
`is_free_for_members` gets the same five variations as any other. The
dashboard's free-admission log is the only record of those seats; a second
count on the register would disagree with it whenever staff skipped one.

Item-level fields:

| Item field | Value |
|---|---|
| `name` | `engagement.display_title` |
| `categories` / `reporting_category` | `SQUARE_TICKET_CATEGORY_ID` (Movies) — always, so the report filter stays one ID |
| `product_type` | `REGULAR` |
| `is_taxable` | `false` (matches every existing ticket item) |
| `present_at_location_ids` | `[SQUARE_LOCATION_ID]` |
| `ecom_visibility` | `HIDDEN` — these are register items, not Square Online listings |

A film that plays twice (a classic revived next year) gets two items with the
same name over time, never at once. Square allows duplicate names; the IDs
and SKUs differ.

### SKUs carry Django's key

Every variation Django writes gets a SKU of the form `fkc-eng-<id>-<tier>`.
The link table is the primary mapping, but the SKU means (a) a variation is
still attributable if a link row is ever lost, (b) the nightly reconcile can
detect a Django-made item it has no row for, and (c) staff can search the SKU
in Square. No existing ticket item has a SKU, so there is no collision with
hand-made items.

### Upserts are idempotent, versioned, and whole

Push uses `batch_upsert` with a fresh idempotency key per call and client
temporary IDs (`#eng-42`, `#eng-42-adult`); Square's `id_mappings` in the
response are written to the link table. An update sends the complete item with
the stored `version`. On `VERSION_MISMATCH` (someone edited the item in
Square), Django fetches the current object, re-applies its own view of the
item on top, and retries once. Django's view wins: the engagement is the
source of truth for name, variations, and prices. The reconcile log notes that
an external edit was overwritten.

### Pull uses Search Orders, not Payments then Orders

The script lists completed payments, de-duplicates order IDs, then batch-gets
the orders. `orders.search` with a `closed_at` date filter and
`state_filter: [COMPLETED]` returns the same orders, line items included, in
one paginated call. Tenders of every kind (card, cash, gift card) are orders,
so nothing is lost.

**Business day** is a calendar day in `America/New_York`, midnight to
midnight, as the script already defines it. The last show ends well before
midnight.

The command pulls the target day **and the two days before it** every night.
Re-pulling is idempotent (see the ledger's unique key), and it catches an
order that closed late or a night the job did not run.

### Attribution by catalog ID; unknown lines stay unattributed

Each stored line item carries Square's `catalog_object_id` (the variation).
If a `SquareVariation` row has that ID, the line is attributed to its
engagement and tier. If not, the line is kept unattributed with its name and
category recorded. Pre-cutover sales, hand-made items, concessions, and
memberships all land there, which is correct: the owner summary still reports
every item, exactly as the script does.

### `admissions` becomes derived for linked runs

After each pull, `Engagement.admissions` is recomputed for every engagement
with a Square item: the sum of quantities across its attributed ticket lines,
all time. Runs with no item (pre-cutover) are not touched, so their hand-typed
value survives. The field stays a column rather than a property so the
existing admin, exports, and any query keep working; the pull is just the
thing that writes it now.

### The ticket report's exclusion list becomes a flag on the run

`EXCLUDED_TICKET_ITEMS` in the script's `.env` exists for runs that owe no
distributor royalty — a Classic Movie Night — and so must stay out of the
report sent to the booker while still appearing in the owner's summary.
That is a property of the engagement: `Engagement.in_ticket_report`
(`BooleanField`, default `True`, help text saying exactly the above). No
environment list of item names to keep in step with titles.

### Report recipients and subjects live in the database

Who receives the nightly reports is a business choice, so it is managed in
the Django admin, not in Ansible. Two models in `boxoffice`:

- **`EmailReport`** — one row per report kind, `OWNER_SUMMARY` and
  `TICKET_REPORT`, each with an editable `subject` and an `enabled` switch.
  The initial migration seeds both rows with the script's current subjects,
  so nothing has to be typed on deploy.
- **`EmailRecipient`** — rows under a report with an `address` and a `cc`
  flag. Adding, removing, or disabling a recipient is a row edit.

Both are registered in `boxoffice/admin.py` the way `cinema/admin.py`
registers its models, with recipients inline on the report. A report that is
disabled or has no recipients is skipped, and the pull's log row says so.

This is the project's first admin-editable settings table. It is two models
rather than a singleton row with four fixed fields because recipient lists
are lists; a third report later is a new choice, not a new column.

### Email arrives in the project, via Django's own backend

This project sends no email today, by decision (voicemail stays in the
dashboard). Flash grosses are different: the ticket report's recipient is
outside the organisation and expects an email each night. Django's SMTP
backend is configured from the environment (`EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`,
`DEFAULT_FROM_EMAIL`); `DEBUG` uses the console backend. How mail is sent is
infrastructure and stays beside the Square and Twilio tokens; who gets it is
the database table above. The two message bodies are ported from the script
into templates under `boxoffice/templates/boxoffice/email/`.

**Both reports go out every night the pull succeeds.** On a day with no
ticket sales the ticket report says so in its body; on a day with no sales
at all the owner summary says so. This differs from the script, which sent
nothing on a quiet day, and means the recipients learn that the pull ran.
Whether each email was sent, and to whom, is recorded on the pull's log row.
The dashboard alert for a failed or missing pull is the backstop.

## Data model

All in `boxoffice/models/`, one file per model, re-exported from `__init__`.

### `SquareItem`

One row per Square catalog item Django owns.

| Field | Type | Notes |
|---|---|---|
| `engagement` | `OneToOneField(Engagement, null=True, on_delete=SET_NULL, related_name="square_item")` | Phase 2 adds `membership_tier`; a check constraint requires exactly one owner |
| `square_id` | `CharField(max_length=64, unique=True)` | catalog object ID |
| `version` | `BigIntegerField` | required on every update |
| `name` | `CharField(max_length=200)` | as last pushed, for the reconcile diff |
| `synced_at` | `DateTimeField(null=True)` | last successful push |
| `last_error` | `TextField(blank=True)` | cleared on success; drives the red pill |
| `deleted_at` | `DateTimeField(null=True)` | set when Django deleted it in Square; the row stays so old sales still resolve |

`SET_NULL` rather than `CASCADE` on the engagement: deleting a run in the
dashboard must not orphan an item in Square. `EngagementDeleteView` calls
`boxoffice.sync.delete(engagement)` first; if that fails the delete is
refused with a message, since a dangling register item is worse than a stuck
dashboard row.

### `SquareVariation`

| Field | Type | Notes |
|---|---|---|
| `item` | `FK(SquareItem, related_name="variations", on_delete=CASCADE)` | |
| `square_id` | `CharField(max_length=64, unique=True)` | variation object ID — what order lines carry |
| `sku` | `CharField(max_length=64, unique=True)` | |
| `tier` | `CharField(max_length=16)` | `adult` … `member`, a key of `TICKET_PRICES` |
| `name` | `CharField(max_length=80)` | as pushed |
| `price_cents` | `PositiveIntegerField` | as pushed |
| `ordinal` | `PositiveSmallIntegerField` | |

`UniqueConstraint(item, tier)`.

### `SaleLine`

The ledger. One row per order line item.

| Field | Type | Notes |
|---|---|---|
| `order_id` | `CharField(max_length=64)` | |
| `line_uid` | `CharField(max_length=64)` | Square's line item `uid` |
| `business_date` | `DateField(db_index=True)` | Eastern calendar day of `closed_at` |
| `closed_at` | `DateTimeField` | |
| `item_name` | `CharField(max_length=200)` | Square's snapshot |
| `variation_name` | `CharField(max_length=80, blank=True)` | |
| `catalog_object_id` | `CharField(max_length=64, blank=True, db_index=True)` | variation ID; blank for ad-hoc amounts |
| `category_id` | `CharField(max_length=64, blank=True)` | resolved from the catalog at pull time |
| `quantity` | `PositiveIntegerField` | Square sends `"1.00000000"`; integer tickets only |
| `gross_cents` | `IntegerField` | `total_money`, after discounts, before tax |
| `variation` | `FK(SquareVariation, null=True, on_delete=SET_NULL)` | attribution |
| `engagement` | `FK(Engagement, null=True, on_delete=SET_NULL)` | denormalised from `variation` for cheap aggregation |

`UniqueConstraint(order_id, line_uid)` is what makes re-pulling a day
idempotent: the pull does `update_or_create` on that pair.

Per-tier daily totals (adult tickets sold, senior tickets sold, …) are a
`GROUP BY variation__tier` over this table for a `business_date`. They are
not stored separately.

### `SalesPull`

The run log. One row per command invocation per business date.

| Field | Type | Notes |
|---|---|---|
| `business_date` | `DateField` | |
| `started_at` / `finished_at` | `DateTimeField` | |
| `status` | `CharField` choices `OK` / `FAILED` | |
| `orders` / `lines` | `PositiveIntegerField` | counts; both zero on a quiet day |
| `owner_email_sent` / `report_email_sent` | `BooleanField` | false when the report is disabled or has no recipients |
| `error` | `TextField(blank=True)` | |

The dashboard reads the most recent row per date. "No pull for yesterday" and
"yesterday's pull failed" are both one query.

### `EmailReport` and `EmailRecipient`

| `EmailReport` field | Type | Notes |
|---|---|---|
| `kind` | `CharField(max_length=20, unique=True)` choices `OWNER_SUMMARY` / `TICKET_REPORT` | |
| `subject` | `CharField(max_length=200)` | |
| `enabled` | `BooleanField(default=True)` | |

| `EmailRecipient` field | Type | Notes |
|---|---|---|
| `report` | `FK(EmailReport, related_name="recipients", on_delete=CASCADE)` | |
| `address` | `EmailField` | |
| `cc` | `BooleanField(default=False)` | |

`UniqueConstraint(report, address)`. The data migration seeds the two
`EmailReport` rows with `"Daily Sales Summary"` and the script's
`TICKET_REPORT_SUBJECT`; recipients are entered in the admin at rollout.

### `Engagement` additions (in `cinema`)

`in_ticket_report` as described above. One migration,
`cinema/0018_engagement_in_ticket_report.py`.

## Services

`boxoffice/sync.py` — the push side.

- `desired_item(engagement) -> ItemSpec`: pure. Builds the item and variation
  spec from the engagement and `TICKET_PRICES`. Fully unit tested with no
  gateway.
- `push(engagement)`: compares `desired_item` with the stored link rows,
  upserts if different, writes IDs and version, clears or sets `last_error`.
- `delete(engagement)`: batch-deletes the item, sets `deleted_at`.
- `schedule(engagement)`: `transaction.on_commit(lambda: push(...))`, swallowing
  and logging gateway errors. What the dashboard views call.
- `reconcile(today)`: for every `CONFIRMED` engagement with `end_date >= today`,
  `push`; for every linked run that is ended, cancelled, or past its end date,
  `delete`; list the ticket category and log any item Django does not own.

`boxoffice/pull.py` — the pull side.

- `pull_day(date) -> SalesPull`: searches orders, resolves variation IDs against
  `SquareVariation`, upserts `SaleLine`s, recomputes `admissions` for touched
  engagements, writes the log row.
- `owner_summary(date)` / `ticket_report(date)`: aggregate `SaleLine` for the
  date into the two report shapes. Pure over the ledger, so they can be re-run
  for any past day without touching Square.
- `send_reports(date, dry_run=False)`: renders and sends each enabled
  `EmailReport` to its recipients, records the result on the `SalesPull`.

## Management commands

| Command | Schedule (Ansible cron, Eastern) | Does |
|---|---|---|
| `pull_square_sales [--date YYYY-MM-DD] [--days 3] [--dry-run] [--no-email]` | 23:45 daily | pulls the date and the `--days - 1` before it; emails for the target date only |
| `sync_square_catalog [--dry-run]` | 02:00 daily | `reconcile(today)` |

`--dry-run` logs every intended Square write or email and performs none.
The cron entries live in the Ansible repo's `webservers.yml`, not here; the
runbook section below lists them.

## Dashboard surface

Deliberately small. Three things, each answering one question.

**Engagement detail: a Square pill.** Grey "Not in Square" for drafts;
green "In Square · 5 variations · synced 2m ago"; red "Square sync failed"
with the error text and a Retry button posting to
`dashboard:engagement_square_retry`. Lives in the existing header block, no
new page.

**Home: a Sales panel.** Yesterday's gross, tickets sold, concessions gross,
and the same three for the same weekday last week, read from `SaleLine`.
Empty state before the first pull: "No sales pulled yet." Hidden entirely
when `SQUARE_ACCESS_TOKEN` is blank, so the dashboard looks unchanged in an
environment without Square.

**Smart alerts** in `dashboard/smart_alerts.py`, same shape as the existing
ones:

- `warning` — "Yesterday's Square sales pull failed" or "No Square sales pull
  ran yesterday", when the token is set and no `OK` row exists for yesterday.
- `warning` — "N runs failed to sync to Square", when any `SquareItem` has a
  `last_error`.

**Engagement form** gains `in_ticket_report` under the existing fields.

**Django admin** gains `EmailReport` with `EmailRecipient` inline.

## Testing

TDD throughout; `python manage.py test` and `flake8` are the gates.

`boxoffice/tests/test_sync_spec.py` — `desired_item`, no gateway:

- yields one variation per priced entry in `TICKET_PRICES`, in order, with
  those prices and `fkc-eng-<id>-<tier>` SKUs
- `matinee_until` is not a variation
- item name is `display_title`; category, location, taxable, visibility fixed

`boxoffice/tests/test_sync.py` — with the fake gateway:

- first push creates; second push with no change makes no gateway call
- a renamed run re-pushes with the stored version
- `VERSION_MISMATCH` fetches, retries once, and wins
- gateway failure sets `last_error`, leaves the engagement saved
- `reconcile` deletes ended/cancelled/past-end-date runs' items and reports
  unknown items without deleting them
- blank token: no gateway call, no error

`boxoffice/tests/test_pull.py` — with the fake gateway returning fixture
orders:

- lines land with the right `business_date` across the midnight boundary
- a second pull of the same day changes nothing (unique key)
- lines with a known variation ID are attributed to engagement and tier;
  unknown IDs are kept unattributed
- per-tier totals for a date match the fixture
- `admissions` is recomputed for linked runs and untouched for unlinked ones
- owner summary totals and ticket report filter (category, `in_ticket_report`)
  match the script's output, run against the script's own sample data
- a no-sales day sends both reports with the "no sales" body; a no-ticket
  day sends the ticket report with the "no ticket sales" body
- a disabled report, or one with no recipients, is skipped and recorded
- `SalesPull` row records status, counts, and emails sent

`boxoffice/tests/test_admin.py`:

- the seed migration creates both `EmailReport` rows with the script's
  subjects
- recipients save with `cc`, duplicate address per report is refused

`dashboard/tests/test_square_views.py`:

- engagement create, edit, and status change call `schedule`; showtime views
  do not
- delete refuses when Square deletion fails
- Retry endpoint is staff-only and calls `push`
- pill states; Sales panel hidden without a token; both alerts

## Rollout

Ship with the token blank, so deploying the code changes nothing visible.

1. **Square side.** Create a Developer application with catalog read/write
   and orders read scopes. Record the production location ID and the Movies
   category ID. Confirm the sandbox equivalents for local use.
2. **Server side.** Add `SQUARE_*` and `EMAIL_*` to `webservers.yml`; deploy;
   `migrate`. In the admin, enter the recipients for both reports. Run
   `sync_square_catalog --dry-run` and read what it would push.
3. **Cutover, on a run boundary.** After the last show of the current runs
   has started: delete every hand-made ticket item in Square (not the Movies
   category); those runs end at their `end_date` and the nightly reconcile
   retires their items; confirm the new week's runs in the dashboard and watch the items appear. Staff pin the new items to the
   register's favorites grid and stop using the matinee discount. The empty
   Events and Pre-Sales categories can be removed in Square or left; Django
   never uses them.
4. **Reports.** Run `pull_square_sales --dry-run` for the cutover day and
   compare against the old script's output for the same day. Then add the two
   cron entries and retire the script's cron.
5. **Verify over the first week** that `admissions` is filling and the
   ticket report matches what the booker received before.

The local database is stale sqlite, not production. Nothing here can be
verified against real sales before the sandbox and the cutover day.

## Phase 2 — memberships (designed, not built)

The five membership tiers already live in `audience.MembershipTier` with a
name, a price, and a hand-pasted `checkout_url`. Square holds the same five
prices on five items, and nothing checks they agree. A reading of the live
payment links also found five API-created links from February with no
redirect configured, none of which match the URLs stored on the tiers.

Phase 2 would:

- add `membership_tier` to `SquareItem` (the check constraint becomes "exactly
  one of `engagement`, `membership_tier`"), with a single `Annual` variation
  at `price`, in the Memberships category, SKU `fkc-tier-<slug>`;
- add `SquarePaymentLink` (tier, link ID, short URL, order ID, `redirect_url`),
  created through the Checkout API's `createPaymentLink` with the variation,
  `redirect_url` set to `/thanks?tier=<slug>`, tipping and shipping off;
- write the short URL into `MembershipTier.checkout_url`, making that field
  read-only in the dashboard form;
- on a price change, create a new link, swap the URL, and delete the old
  link, because a link's order is frozen at creation and must not keep
  charging the old price;
- attribute membership `SaleLine`s to tiers, giving the roster a "paid in
  Square, no term entered" alert — the reconciliation the spreadsheet
  replacement was waiting for.

Nothing in Phase 1 needs to change for this; it is additive.

## Decisions log (2026-10-05 review)

- Push on confirmation, not creation. Drafts get no item.
- Per-showtime ticket items are out of scope for this project.
- Every line item is stored; per-tier totals are derived.
- Both reports carry over; the exclusion list becomes `in_ticket_report`.
- Matinee is its own priced variation, not a discount.
- Free-for-members runs get no $0 variation; the free-admission log is the
  only record.
- Report recipients and subjects are managed in the Django admin.
- Both reports send nightly; a quiet day's email says so.
- Senior members pay $4 and ring as Member. New priced tiers are new entries
  in `TICKET_PRICES`, nothing more.

## Amendments (implementation, 2026-10-05)

- `SquareItem.engagement` is a foreign key with a partial unique constraint
  ("one live item per engagement", where `deleted_at` is null) instead of a
  OneToOne, so a retired row can sit beside the live one.
- `SquareItem.square_id` is nullable: a row for a push that never created an
  item carries `last_error` and no Square ID.
- `ecom_visibility` is not sent: SDK 42 has no such key.
- `SquareVariation.sku` is not unique: a re-confirmed run reuses its SKUs on
  a fresh item, and the retired row keeps the old ones so old sales resolve.
- The engagement has no `ENDED` status; "ended" means today > `end_date`.
- The Retry button runs the full sync (push or delete, by the state table),
  not a bare push.
- The pill has a fifth state: a live row with no Square ID and no error shows
  as failed, with Retry.
- Dashboard toasts travel in the `HX-Trigger` header. A save whose Square
  sync failed says "Saved. Square sync failed — see the run".
- A re-pull keeps a line's existing attribution when its variation no longer
  resolves, and recomputes admissions for engagements that lost lines.
- A `SalesPull` row is created `FAILED` ("Pull did not finish") and flipped
  to `OK` on completion, so a killed pull still raises the dashboard alert.
- Email failures are recorded on `pull.error` with the status left `OK`.
- The nightly reconcile also restores items deleted or moved out of the
  ticket category by hand in Square, and retires live rows whose engagement
  was deleted outside the dashboard; one bad row is reported and skipped.
- `typing_extensions` is pinned to 4.16.0 (the SDK's `anyio` needs it).
