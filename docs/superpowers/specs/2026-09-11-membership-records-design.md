# Membership Records — members, terms, and a dashboard roster — Design

**Date:** 2026-09-11
**Status:** Awaiting user review (design phase)
**Repo:** `api_fortkentcinema_com` (branch: new `feat/membership-records`)

## Context

Memberships are sold through five Square payment links listed in
`web/constants.py:MEMBERSHIP`. The site renders the tiers and their perks at
`/membership/`, Square takes the money, and `/thanks?tier=<slug>` catches the
redirect. Nothing about who actually bought a membership comes back into this
application — the roster lives in a spreadsheet, and the box office looks people
up by name, as the FAQ copy on the page says.

This replaces the spreadsheet with a real record. The goal for the first version
is narrow and was stated as such: **a reliable record**, not a point-of-sale tool.
Staff add members through the dashboard, renewals append to a history, and the
roster exports to CSV.

### Explicitly out of scope

- **Box-office lookup.** No counter-optimized search screen. The roster list has a
  filter box, which is enough to find someone, but the fast name-lookup workflow is
  a later feature that this data model is designed to support.
- **Member-facing accounts.** No logins, no self-serve card, no emails. That means
  auth, password resets, and a privacy surface that a roster does not need.
- **Square integration.** No API calls, no webhook, no automatic member creation on
  purchase. Square is a payment link today and nothing in the codebase talks to its
  API; the roster is typed in by hand.
- **Bulk import.** The existing spreadsheet is entered manually, once. An importer
  is code to write, test, and maintain for a job that happens a single time.
- **Family/household members.** Family tiers stay honor-system, exactly as they work
  now at the counter. Only the cardholder is stored.

## Decisions

### Members live in `audience`, not a new app

`audience` exists to hold people who are not staff. Its `Subscriber` docstring says
it is deliberately generic so the next feature needing people reuses the app rather
than growing its own. Two models do not justify a seventh app, and if membership
later grows a lookup screen or member logins, moving it out then is a rename, not a
rewrite.

`audience/models.py` becomes a `models/` package mirroring `cinema/models/` —
`subscriber.py` moves in unchanged and `__init__.py` re-exports, so every existing
`from audience.models import Subscriber` keeps working and each model gets a focused
file. Same app label and same table names, so this generates **no migration**.

### Members and subscribers stay unlinked

Paying for a membership is not an opt-in to marketing email. `Subscriber` already
refuses to resurrect an address that unsubscribed, and auto-creating subscriber rows
from purchases would drive straight through that intent. The two models share no
foreign key. Members can be exported and mailed deliberately if that is ever wanted.

### A member has many terms

A renewal appends a `MembershipTerm` rather than moving dates on the member. One row
per purchase means renewals, tier changes, lapses, and year-over-year retention all
fall out of the data instead of being lost on overwrite. Last year's term stays
visible above this year's on the member's page.

### Status is derived, never stored

There is no `is_active` column. A stored flag goes stale silently at midnight on
every expiry and needs a scheduled job to stay honest; a derived one is correct every
time the page loads, and "lapsed" is a query. The cost is that a member cannot be
hand-flagged active without editing a term's dates — which is right, because the
dates are the truth.

**Expiry is inclusive.** A membership is good *through* `expires_on`, not up to it.

### Tier is a slug, validated at the form layer

`web` imports `audience` (`web/views.py:15`), so `audience` importing `web.constants`
would be circular. `MembershipTerm.tier` is therefore a plain `CharField` holding the
tier slug, and `dashboard/forms.py` builds the dropdown from `MEMBERSHIP` —
`dashboard` importing `web` is a safe direction, since `web` does not import
`dashboard`. The tier catalog stays exactly where it is today.

`price_paid` is stored on the term, defaulted from the tier but editable, so a comped
or discounted membership records what actually changed hands and past revenue
survives a future price change. `expires_on` likewise defaults to `started_on` plus
the tier's `duration_months` but stays editable — every tier is 12 months today, and
hardcoding that would break the first half-year membership sold.

## Data model

### `audience/models/member.py`

| Field | Type | Notes |
|---|---|---|
| `first_name` | `CharField` | required |
| `last_name` | `CharField` | required; list sorts on it |
| `email` | `EmailField(unique=True)` | required; lowercased in `save()`, as `Subscriber` does |
| `phone` | `CharField(blank=True)` | free text — validation buys nothing for a local roster |
| `notes` | `TextField(blank=True)` | the miscellany column every spreadsheet has |
| `created_at` / `updated_at` | `DateTimeField` | `auto_now_add` / `auto_now` |

Derived, not stored:

- `current_term` — the term whose date range covers today, or `None`
- `is_active` — `current_term is not None`

`MemberManager` provides `.active()` and `.lapsed()` so the list view and any export
filter through one definition, mirroring `SubscriberManager.active()`.

`Meta.ordering = ["last_name", "first_name"]`.

### `audience/models/membership_term.py`

| Field | Type | Notes |
|---|---|---|
| `member` | `FK(Member, related_name="terms", on_delete=CASCADE)` | a term without its person is meaningless |
| `tier` | `CharField(max_length=32)` | slug from `MEMBERSHIP`; validated in the form |
| `started_on` | `DateField` | day granularity — a membership is not a timestamp |
| `expires_on` | `DateField` | inclusive; defaults to start + tier duration |
| `price_paid` | `DecimalField(max_digits=7, decimal_places=2)` | what actually changed hands |
| `purchased_at` | `DateField(null=True, blank=True)` | optional |
| `notes` | `TextField(blank=True)` | optional |

`Meta.ordering = ["-started_on"]`.

Overlapping terms are not rejected. Staff double-entering a renewal is a data-entry
mistake to notice in the UI, not an integrity violation worth a constraint that would
also block a legitimate early renewal.

Migration: `audience/0002_member_membershipterm.py`. Nothing to backfill.

## Dashboard surface

Follows the Screens CRUD pattern in `dashboard/views.py:149-195` — drawer form, htmx
out-of-band list swap, `HX-Trigger` toast. Nothing new is invented in the UI layer.

**New module:** `dashboard/member_views.py`, kept out of `views.py` (already 600+
lines) for the same reason `poll_views.py` and `subscriber_views.py` are separate.

| View | URL | Purpose |
|---|---|---|
| `MemberListView` | `members` | roster with `?q=` and status filter (defaults to all members) |
| `MemberDetailView` | `members/<pk>` | contact block + terms, newest first |
| `MemberCreateView` | `members/new` | drawer form |
| `MemberEditView` | `members/<pk>/edit` | drawer form |
| `MemberDeleteView` | `members/<pk>/delete` | confirm, cascades to terms |
| `TermCreateView` | `members/<pk>/terms/new` | the renewal path |
| `TermEditView` | `terms/<pk>/edit` | fix a typo'd date |
| `TermDeleteView` | `terms/<pk>/delete` | remove a mistaken term |
| `MemberExportView` | `members/export.csv` | one row per member |

**Templates:** `members.html`, `_member_list.html`, `_member_form.html`,
`member_detail.html`, `_term_list.html`, `_term_form.html`.

**Forms** in the existing `dashboard/forms.py`: `MemberForm` and `MembershipTermForm`,
the latter sourcing its tier choices from `MEMBERSHIP` and its price/expiry defaults
from the selected tier.

**Two screens, not one.** Terms do not fit on a list row. The roster shows surname,
email, tier, expiry, and a status pill; clicking through opens the member, where
renewals are added. Status pill states: Active, Expiring soon (**within 30 days**),
Lapsed. The window affects only the pill's colour — nothing is emailed.

**Delete confirms rather than protects.** Screens refuse deletion via `ProtectedError`;
that is wrong here. A person entered by mistake should be removable, and their term
rows exist only to describe them. The confirm drawer states how many terms will go.

**CSV export** — name, email, phone, tier, started, expires, price paid — one row per
member drawn from their most recent term, matching the shape of the spreadsheet being
replaced. A per-term export for revenue analysis is a later, small addition.

**Sidebar** gets a Members link between Subscribers and Inquiries, using the same
inline-SVG convention as its neighbours.

## Privacy

This is the first real customer PII in the database: names, emails, and phone numbers
of paying members. Every view above, the CSV export included, sits behind
`StaffRequiredMixin`. Nothing renders on the public site, and no member data is
exposed through any public URL, sitemap, or template context.

## Testing

TDD throughout. Two new test files; `python manage.py test` and `flake8` are the
gates that actually run in this project.

`audience/tests/test_member.py`

- email lowercased on save; duplicate email rejected
- `current_term` / `is_active` on the start date, on the expiry date (inclusive), and
  the day after
- a member with one lapsed and one current term reads active, and `current_term`
  returns the current one
- `.active()` and `.lapsed()` partition the roster with no overlap
- `expires_on` defaults to start + `duration_months`; an explicit value survives

`dashboard/tests/test_member_views.py`

- every URL redirects anonymous users and 403s authenticated non-staff
- create / edit / delete happy paths; deleting a member deletes their terms
- adding a term to an existing member — the renewal path
- the form rejects a tier slug absent from `MEMBERSHIP`
- CSV export: header row, one row per member, reflects the latest term
- `?q=` matches on both name and email

## Rollout

No environment variables, no third-party configuration, no Square changes. Deploy is
`migrate` and nothing else. The roster is entered by hand afterwards.

The local database is stale sqlite, not production, so nothing here can be verified
against real membership data before deploy.

**Branch hygiene:** the working tree currently carries uncommitted
`is_free_for_members` work (`cinema/models/engagement.py`, `cinema/admin.py`,
`dashboard/forms.py`, and untracked `cinema/migrations/0011_*`). That work must be
committed or stashed before this branch starts, so the two migrations and the two
sets of `dashboard/forms.py` changes do not tangle.
