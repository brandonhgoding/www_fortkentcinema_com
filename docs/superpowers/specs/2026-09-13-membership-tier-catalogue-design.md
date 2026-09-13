# Membership Tier Catalogue — moving tiers out of `web.constants` and into the database — Design

**Date:** 2026-09-13
**Status:** Awaiting user review (design phase)
**Repo:** `api_fortkentcinema_com` (branch: new `feat/membership-tier-catalogue`)
**Supersedes:** the "Tier is a slug, validated at the form layer" decision in
`docs/superpowers/specs/2026-09-11-membership-records-design.md`

## Context

The membership tier catalogue is a Python literal. `web/constants.py:MEMBERSHIP`
holds five dicts — name, price, perks, and the Square payment link for each tier —
and three things read it: the public `/membership/` page renders the cards from it,
`/thanks?tier=<slug>` looks up a purchase value from it, and `dashboard/forms.py`
builds the roster's tier dropdown from it.

Work already in the tree (uncommitted on `main`) starts moving that catalogue into
the `audience` app: `MembershipBenefit` and `MembershipTier` models, migrations 0003
and 0004, and a `MembershipTerm.tier` foreign key replacing the slug `CharField`.

That start is incomplete in a way that blocks it from rendering the page. The card
partial reads nine fields per tier; `MembershipTier` has one of them. Changing a
price or adding a perk still means editing Python and deploying — the thing moving
to the database was supposed to end.

This finishes the move: the database becomes the only catalogue, the constant is
deleted, and the rendered page does not change by a single character.

### Explicitly out of scope

- **Editing tiers in the dashboard.** Django admin is registered and is enough.
  A staff-facing tier CRUD screen is a later feature if the admin proves awkward.
- **Square API integration.** `checkout_url` stays a URL typed in by hand. Nothing
  in this codebase talks to Square's API and this change does not start.
- **Per-tier benefit ordering.** Benefits sort globally. See the decision below.
- **Touching `MEMBERSHIP_FAQ`.** The FAQ is prose, not catalogue data, and stays a
  constant.
- **Member-visible changes of any kind.** This is a refactor. The acceptance test
  is that `/membership/` renders identically.

## Decisions

### Field names match the template

`MembershipTier` gets its fields named exactly as `templates/partials/tier_card.html`
already reads them — `slug`, `name`, `eyebrow`, `price`, `duration_months`,
`featured`, `is_family_tier`, `checkout_url`. A model instance then substitutes for
a catalogue dict with no template churn: the only edit the partial needs is the perk
loop, because `tier.perks` (a list of strings) becomes `tier.benefits.all` (a
queryset of objects).

This is the cheapest possible diff on the one file whose output must not change.

### `price` is an integer, not a decimal

The card renders `${{ tier.price }}`. A `DecimalField` would render `$35.00` where
the page says `$35`, changing every price on a live page during what is supposed to
be an invisible refactor. `PositiveIntegerField` preserves the output exactly.

Tier price is a list price in whole dollars. `MembershipTerm.price_paid` stays a
`DecimalField` — that one records what actually changed hands, including comped and
prorated amounts, and is a different quantity.

### Benefits sort globally, not per tier

Ten distinct perk strings appear across the five tiers, and they always appear in the
same category order: matinee, evening, small popcorn, medium & large popcorn,
birthday, rentals. Tiers differ in *which* variant they carry ("$1 off evening" vs
"$4 off evening"), never in the order.

So `MembershipBenefit` carries a `sort_order` and the variants of a category share a
value:

```
10  $2 off matinee tickets              (all five tiers)
20  $1 off evening tickets              (Silver Screen)
20  $4 off evening tickets              (the other four)
30  $1 off small popcorn                (all five)
40  $1 off medium & large popcorn       (Silver Screen)
40  $2 off medium & large popcorn       (the other four)
50  Free small popcorn during your birthday month
60  10% / 15% / 20% off rentals
```

`Meta.ordering = ["sort_order", "name"]` then produces the right list for every tier
from a plain `ManyToManyField`.

The alternative — a through model with a per-tier position — buys the freedom to
order one tier's perks differently from another's. Nothing in five years of this
catalogue has wanted that, and it costs a second model, an inline admin, and a more
complicated seed. Rejected as YAGNI. If a tier ever needs its own order, converting
a plain M2M to a `through` model is a contained change.

### `on_delete=PROTECT` on `MembershipTerm.tier`

The uncommitted work has `CASCADE`, which means deleting a tier deletes every
membership term ever sold under it — dates, `price_paid`, the lot. Membership terms
are revenue records.

`PROTECT` refuses the delete instead, and `show_on_membership_page` is the correct way
to retire a tier: the tier stops appearing on the public page, historical terms keep
pointing at it and keep rendering their tier name. This matters concretely here —
the membership program was discontinued in August 2026 and reinstated eight days
later. Retiring is a thing that actually happens; deleting is not.

`null=False`: every term has a tier. The field is nullable only transiently inside
the migration sequence below.

### `show_on_membership_page`, not `hidden`

The field started life as `hidden`, which reads as "hidden everywhere" and is wrong:
a retired tier must stay fully visible in the admin and the dashboard, because
historical terms still point at it and staff still have to read and edit them.

This codebase already has exactly this flag under a positive name —
`Engagement.show_in_main_listings`, named for the surface it controls and defaulting
to `True`. `MembershipTier.show_on_membership_page` follows it, and reading
`show_on_membership_page=False` beats reading `hidden=False` for a visible tier.

Turning it off excludes a tier from `/membership/` and nothing else. It does not
hide historical terms, does not remove the tier from the dashboard's tier dropdown
when an existing term already uses it, does not touch the admin, and does not affect
`/thanks` — a Square link for a retired tier that someone still has bookmarked
resolves and attributes correctly.

### The seed data is copied into the migration

`audience` must never import `web` — `web/views.py:15` imports `audience.models`, so
the reverse is circular. The seed migration therefore carries its own literal copy of
the five tiers rather than importing `MEMBERSHIP`.

This is also how migrations should be written regardless: a migration that imports
application code breaks the moment that code changes, and this particular constant is
deleted in the same change.

### The CharField→FK swap is a four-step migration

Production has almost certainly zero `MembershipTerm` rows — `audience.0002` is on
`origin/main` but has never been deployed, and the roster is typed in by hand after
deploy. "Almost certainly" is not the standard for revenue records, and the cost of
being careful is one extra migration.

So: add a nullable FK alongside the existing `CharField`, copy across by matching
slug, drop the `CharField`, rename the FK into its place. A bare `AlterField` from
`varchar` to an integer FK would drop every value it could not cast.

The existing uncommitted migrations 0003 and 0004 are replaced rather than built on.
Neither has been deployed anywhere, 0004 contains exactly the `CASCADE` and bare
`AlterField` this design rejects, and a clean sequence is easier to read than a
correction layered on a mistake.

## Data model

### `audience/models/membership_benefit.py`

```python
class MembershipBenefit(models.Model):
    name = models.CharField(max_length=255)          # the perk line as rendered
    description = models.TextField(blank=True)       # admin-only context
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
```

`name` is the string the card prints. `description` is not rendered anywhere on the
public site; it exists so a staff member can explain a perk to another staff member.

### `audience/models/membership_tier.py`

```python
class MembershipTier(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=45)
    eyebrow = models.CharField(max_length=60, blank=True)
    description = models.TextField(blank=True)
    price = models.PositiveIntegerField()            # whole dollars
    duration_months = models.PositiveSmallIntegerField(default=12)
    featured = models.BooleanField(default=False)    # "Best Value" ribbon
    is_family_tier = models.BooleanField(default=False)  # "For Families" ribbon
    checkout_url = models.URLField(blank=True)
    benefits = models.ManyToManyField(MembershipBenefit, blank=True)
    show_on_membership_page = models.BooleanField(
        default=True,
        help_text="Show this tier on the public membership page. Turn off to "
                  "retire a tier: it stays in the admin and dashboard, and "
                  "historical terms keep pointing at it.",
    )
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price"]
```

`slug` is load-bearing beyond the page: Square redirects to
`/thanks?tier=<slug>` and the Join button carries `data-track-tier="<slug>"` for
GA4 attribution. The five existing slugs — `silver-screen`, `individual`,
`cinema-supporter`, `family`, `family-plus` — are configured in the Square dashboard
and **must not change**.

### `audience/models/membership_term.py`

```python
    tier = models.ForeignKey(
        "audience.MembershipTier",
        related_name="terms",
        on_delete=models.PROTECT,
    )
```

`default_expiry(started_on, duration_months)` is unchanged — it already takes the
duration as an argument rather than reading the catalogue.

## Migrations

| | |
|---|---|
| `0003` | Create `MembershipBenefit` and `MembershipTier` with all fields above |
| `0004` | Seed ten benefits and five tiers from literal data; wire the M2M |
| `0005` | Add nullable `tier_fk`; copy from the `tier` slug column; drop `tier`; rename `tier_fk` → `tier`; set `PROTECT`/`null=False` |

0004 is reversible (delete the seeded rows). 0005's data step is reversible by
writing slugs back into a restored `CharField`.

## Consumer changes

| Site | Now | After |
|---|---|---|
| `web/views.py` `MembershipView` | `ctx["tiers"] = MEMBERSHIP` | `MembershipTier.objects.filter(show_on_membership_page=True).prefetch_related("benefits")` |
| `web/views.py` `ThanksView` | `next(t for t in MEMBERSHIP ...)` | `MembershipTier.objects.filter(slug=slug).first()` — **no visibility filter**, so a bookmarked link to a retired tier still attributes |
| `dashboard/forms.py` | `MEMBERSHIP_TIER_CHOICES` | `ModelChoiceField(queryset=MembershipTier.objects.filter(show_on_membership_page=True))`, widened to include the instance's own tier when editing a term on a retired one |
| `dashboard/forms.py` `clean()` | `MEMBERSHIP_BY_SLUG[...]["duration_months"]` | `tier.duration_months` |
| `dashboard/member_views.py` ×4 | `tier_labels` dict in context | removed; templates read `term.tier.name` |
| `templates/partials/tier_card.html` | `{% for perk in tier.perks %}` | `{% for perk in tier.benefits.all %}` / `{{ perk.name }}` |
| `dashboard/member_views.py` CSV | `term.tier` (a slug) | `term.tier.slug` — column stays byte-identical |

`web/constants.py` then loses `MEMBERSHIP`, `MEMBERSHIP_BY_SLUG` and
`MEMBERSHIP_TIER_LABELS`. `MEMBERSHIP_FAQ` stays.

`ThanksView`'s docstring says the purchase value "is looked up server-side from
MEMBERSHIP by slug and is never read from the query string". That property must
survive: the price still comes from the database row, never from the URL.

## Testing

TDD throughout. The suite is `.venv/bin/python manage.py test`; lint is
`.venv/bin/python -m flake8`.

**The acceptance test — the page does not change.** A test asserting `/membership/`
renders all five tier names, all five prices as `$35`…`$250`, every perk string in
its current order, and all five Square URLs. This is the test that makes the refactor
provable rather than hopeful, and it is written against the current constant-driven
page *before* anything moves, so it passes both before and after.

Also covered:

- Benefit and tier ordering come out in catalogue order from a plain M2M.
- `show_on_membership_page=False` drops a tier from `/membership/` and leaves its
  historical terms
  and `/thanks` lookup intact.
- `/thanks?tier=<slug>` resolves a known slug, renders generically for an unknown or
  missing one, and takes its value from the row rather than the query string.
- Deleting a tier that has terms raises `ProtectedError`.
- The term form's choices come from the database, and `expires_on` defaults from the
  selected tier's `duration_months`.
- The CSV export's `tier` column still contains slugs.
- The seed migration produces exactly five tiers and ten benefits with the right
  wiring. Asserted against the migrated test database directly — Django runs all
  migrations to build it, so the seeded rows are simply present and a plain
  `TestCase` can count and inspect them. No migration-executor harness.

The six existing flake8 violations in the uncommitted files — two missing EOF
newlines, two `E302`, two `E501` — are fixed as those files are rewritten.

## Rollout

`manage.py migrate` and nothing else. No environment variables, no Square
reconfiguration, no template deploy ordering concerns.

**Sequencing constraint:** this must reach production in the same deploy as
`audience.0002` — or at least before anyone types members into the roster. If terms
exist with slugs that do not match a seeded tier, migration 0005's copy step leaves
them unmatched. The migration will refuse rather than guess, and the deploy fails
loudly instead of silently dropping tier data.

The local database is stale sqlite, not production; nothing here can be verified
against real membership data before deploy. The acceptance test is the substitute.
