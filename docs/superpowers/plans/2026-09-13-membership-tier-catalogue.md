# Membership Tier Catalogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the membership tier catalogue out of `web.constants.MEMBERSHIP` and into the `audience` app's database tables, so the database is the only catalogue — without changing a single character of what `/membership/` renders.

**Architecture:** `MembershipTier` and `MembershipBenefit` gain the fields `templates/partials/tier_card.html` already reads, so a model instance substitutes for a catalogue dict with almost no template churn. A seed migration carries a literal copy of the five current tiers. `MembershipTerm.tier` becomes a `PROTECT` foreign key via a safe four-step migration. A characterization test written in Task 1 against the *current* constant-driven page is the proof that nothing visible changed.

**Tech Stack:** Django 5.2.3, Django templates, `manage.py test` + `flake8`.

**Spec:** `docs/superpowers/specs/2026-09-13-membership-tier-catalogue-design.md`

## Global Constraints

- **Python is `.venv/bin/python`.** There is no bare `python` on this machine. Every command runs from the repo root.
- **Tests:** `.venv/bin/python manage.py test <label> -v 2`. Full suite: `.venv/bin/python manage.py test`.
- **Lint:** `.venv/bin/python -m flake8 <paths>` — `max-line-length = 88`, migrations excluded. mypy is configured but cannot run in this checkout; do not attempt it. black is configured but unapplied; do not reformat files you did not write.
- **The dashboard has pre-existing flake8 violations** in files this plan does not own (`dashboard/views.py`, `dashboard/urls.py`, `dashboard/tests/test_engagements.py`, and others). Lint only the paths each task names, and never "fix" an unrelated file.
- **`audience` must never import `web`.** `web/views.py:15` imports `audience.models`, so the reverse is circular. Seed data is copied *into* the migration, never imported.
- **The five tier slugs must not change:** `silver-screen`, `individual`, `cinema-supporter`, `family`, `family-plus`. They are configured in the Square dashboard and carried in GA4 `data-track-tier` attributes.
- **`price` is a whole-dollar integer.** The card renders `${{ tier.price }}`; a decimal would print `$35.00` where the live page says `$35`.
- **Expiry is inclusive.** A membership is valid *through* `expires_on`.
- **This is a refactor.** If `/membership/` output changes, the change is wrong.

---

### Task 1: Lock the current page with a characterization test

The safety net for everything after it. This test asserts what `/membership/` renders **today**, from the constant. It must pass now, and still pass unchanged at the end of Task 7 when the page renders from the database. It deliberately hardcodes its expectations rather than importing `MEMBERSHIP` — a test that reads the same source as the code proves nothing.

**Files:**
- Create: `web/tests/test_membership_catalogue.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `EXPECTED_TIERS` — the golden catalogue, reused by Task 3's seed test.

- [ ] **Step 1: Write the characterization test**

Create `web/tests/test_membership_catalogue.py`:

```python
"""What /membership/ renders, pinned.

Written against the constant-driven page and left untouched when the
catalogue moves into the database. If this still passes afterwards, the
refactor was invisible to visitors, which is the entire goal.

It hardcodes its expectations on purpose. Importing web.constants here
would mean asserting the page matches the thing that generated it.
"""

from html import unescape

from django.test import TestCase
from django.urls import reverse

# (slug, name, eyebrow, price, featured, is_family, checkout_url, perks)
EXPECTED_TIERS = [
    (
        "silver-screen", "Silver Screen", "Seniors 65+", 35, False, False,
        "https://square.link/u/UnQLNeHp",
        [
            "$2 off matinee tickets",
            "$1 off evening tickets",
            "$1 off small popcorn",
            "$1 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "10% off rentals",
        ],
    ),
    (
        "individual", "Individual", "", 60, False, False,
        "https://square.link/u/zricPsRR",
        [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "10% off rentals",
        ],
    ),
    (
        "cinema-supporter", "Cinema Supporter", "", 120, True, False,
        "https://square.link/u/2HnpAb9N",
        [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "15% off rentals & parties",
        ],
    ),
    (
        "family", "Family", "", 150, False, True,
        "https://square.link/u/FkcUasKu",
        [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "15% off rentals & parties",
        ],
    ),
    (
        "family-plus", "Family Plus", "", 250, False, True,
        "https://square.link/u/1YSgMFSQ",
        [
            "$2 off matinee tickets",
            "$4 off evening tickets",
            "$1 off small popcorn",
            "$2 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "20% off rentals & parties",
        ],
    ),
]


class MembershipPageIsUnchangedTests(TestCase):
    def setUp(self) -> None:
        # Unescaped, so the expectations below stay the literal catalogue
        # wording. Django renders "&" as "&amp;", and asserting against the
        # entity would mean the test no longer reads like the copy it pins.
        self.html = unescape(
            self.client.get(reverse("membership")).content.decode()
        )

    def test_every_tier_name_is_present(self) -> None:
        for _slug, name, *_rest in EXPECTED_TIERS:
            self.assertIn(name, self.html)

    def test_prices_render_as_whole_dollars(self) -> None:
        for _slug, name, _eyebrow, price, *_rest in EXPECTED_TIERS:
            self.assertIn(f"${price}", self.html, f"{name} price")
            self.assertNotIn(f"${price}.00", self.html, f"{name} price is decimal")

    def test_every_perk_is_present(self) -> None:
        for *_head, perks in EXPECTED_TIERS:
            for perk in perks:
                self.assertIn(perk, self.html)

    def test_perks_appear_in_catalogue_order_within_each_card(self) -> None:
        """Ordering is the thing a plain ManyToManyField would scramble."""
        for slug, name, _eyebrow, _price, _f, _fam, _url, perks in EXPECTED_TIERS:
            card = self.card_for(slug)
            positions = [card.index(p) for p in perks]
            self.assertEqual(
                positions, sorted(positions), f"{name} perks are out of order"
            )

    def test_every_checkout_url_is_present(self) -> None:
        for *_head, url, _perks in EXPECTED_TIERS:
            self.assertIn(url, self.html)

    def test_tiers_appear_in_price_order(self) -> None:
        positions = [self.html.index(f'data-track-tier="{t[0]}"')
                     for t in EXPECTED_TIERS]
        self.assertEqual(positions, sorted(positions))

    def test_ribbons(self) -> None:
        self.assertIn("Best Value", self.html)
        self.assertIn("For Families", self.html)

    def test_eyebrow_and_its_fallback(self) -> None:
        self.assertIn("Seniors 65+", self.html)
        self.assertIn("Patron Card", self.html)  # every tier without an eyebrow

    def card_for(self, slug: str) -> str:
        """The slice of HTML belonging to one tier card.

        Cards are <article> elements and the slug appears only in the Join
        link at the end of one, so a card runs from the previous article
        boundary up to its own slug.
        """
        end = self.html.index(f'data-track-tier="{slug}"')
        start = self.html.rindex("<article", 0, end)
        return self.html[start:end]
```

- [ ] **Step 2: Run it against the current, unchanged page**

Run: `.venv/bin/python manage.py test web.tests.test_membership_catalogue -v 2`
Expected: **PASS**, 8 tests. This is a characterization test; it passes before any change. If it fails now, the expectations above are wrong — fix them to match reality before going further, because everything downstream trusts this file.

- [ ] **Step 3: Lint**

Run: `.venv/bin/python -m flake8 web/tests/test_membership_catalogue.py`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add web/tests/test_membership_catalogue.py
git commit -m "test(web): pin what the membership page renders

A characterization test written against the constant-driven page, to be
left untouched while the catalogue moves into the database. If it still
passes afterwards, the refactor was invisible to visitors.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 2: The two catalogue models

Rewrites the two uncommitted model files with the full field set and replaces the uncommitted migrations 0003 and 0004. Nothing reads these models yet, so the suite stays green throughout.

**Files:**
- Modify: `audience/models/membership_benefit.py` (full rewrite)
- Modify: `audience/models/membership_tier.py` (full rewrite)
- Modify: `audience/admin.py`
- Delete: `audience/migrations/0003_membershipbenefit_membershiptier.py`
- Delete: `audience/migrations/0004_membershiptier_hidden_alter_membershipterm_tier.py`
- Create: `audience/migrations/0003_membershipbenefit_membershiptier.py` (regenerated)
- Test: `audience/tests/test_membership_tier.py`

**Interfaces:**
- Produces: `MembershipTier(slug, name, eyebrow, description, price, duration_months, featured, is_family_tier, checkout_url, benefits, show_on_membership_page, sort_order)` and `MembershipBenefit(name, description, sort_order)`, both exported from `audience.models`.

- [ ] **Step 1: Delete the two uncommitted migrations**

They are replaced, not built on: neither has been applied anywhere, and 0004 contains the `CASCADE` and the bare `CharField`→FK `AlterField` the spec rejects.

```bash
rm audience/migrations/0003_membershipbenefit_membershiptier.py
rm audience/migrations/0004_membershiptier_hidden_alter_membershipterm_tier.py
```

- [ ] **Step 2: Put `MembershipTerm.tier` back to a slug string**

The sketch this branch starts from changed `MembershipTerm.tier` to a foreign
key without a coherent migration. Task 4 does that conversion properly. Leaving
the sketch's version in place here would make Step 7 below generate a migration
touching `membershipterm`, and Task 3's `makemigrations --check` would report
pending changes.

So restore the field in `audience/models/membership_term.py` to exactly what
migration 0002 created, comment included:

```python
    # The tier slug from web.constants.MEMBERSHIP. Stored as a plain string
    # because `web` imports `audience` — validating against the catalogue
    # happens in dashboard.forms, where importing `web` is safe.
    tier = models.CharField(max_length=32)
```

Also restore the blank line the sketch removed above `class MembershipTerm` —
there must be **two** blank lines after the `add_months` import.

This clears the 34 errors the branch starts with, because the tests that assign
`tier="individual"` work again. Task 4 updates them when the field really does
become a foreign key.

Run: `.venv/bin/python manage.py test audience dashboard`
Expected: PASS. Note the count; Task 4 changes it again.

- [ ] **Step 3: Write the failing tests**

Create `audience/tests/test_membership_tier.py`:

```python
from django.test import TestCase

from audience.models import MembershipBenefit, MembershipTier


def make_benefit(name="$2 off matinee tickets", sort_order=10, **kw):
    return MembershipBenefit.objects.create(
        name=name, sort_order=sort_order, **kw
    )


def make_tier(slug="individual", name="Individual", price=60, **kw):
    return MembershipTier.objects.create(
        slug=slug, name=name, price=price, **kw
    )


class MembershipBenefitTests(TestCase):
    def test_str_is_the_name(self) -> None:
        self.assertEqual(str(make_benefit()), "$2 off matinee tickets")

    def test_description_is_optional(self) -> None:
        """Nothing on the public page renders it."""
        self.assertEqual(make_benefit().description, "")

    def test_ordering_is_by_sort_order_then_name(self) -> None:
        make_benefit(name="20% off rentals & parties", sort_order=60)
        make_benefit(name="$4 off evening tickets", sort_order=20)
        make_benefit(name="$2 off matinee tickets", sort_order=10)
        make_benefit(name="10% off rentals", sort_order=60)
        self.assertEqual(
            [b.name for b in MembershipBenefit.objects.all()],
            [
                "$2 off matinee tickets",
                "$4 off evening tickets",
                "10% off rentals",
                "20% off rentals & parties",
            ],
        )


class MembershipTierTests(TestCase):
    def test_str_is_the_name(self) -> None:
        self.assertEqual(str(make_tier()), "Individual")

    def test_slug_is_unique(self) -> None:
        from django.db import IntegrityError, transaction

        make_tier()
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_tier(name="Duplicate")

    def test_defaults(self) -> None:
        tier = make_tier()
        self.assertEqual(tier.duration_months, 12)
        self.assertFalse(tier.featured)
        self.assertFalse(tier.is_family_tier)
        self.assertEqual(tier.eyebrow, "")
        self.assertEqual(tier.checkout_url, "")

    def test_shown_on_the_membership_page_by_default(self) -> None:
        """Retiring is the deliberate act; being listed is the norm."""
        self.assertTrue(make_tier().show_on_membership_page)

    def test_price_is_a_whole_number(self) -> None:
        """$35, never $35.00 — the card renders it raw."""
        self.assertEqual(make_tier(price=35).price, 35)
        self.assertNotIn(".", str(make_tier(slug="x", price=35).price))

    def test_ordering_is_by_sort_order_then_price(self) -> None:
        make_tier(slug="family-plus", name="Family Plus", price=250, sort_order=50)
        make_tier(slug="silver-screen", name="Silver Screen", price=35, sort_order=10)
        make_tier(slug="individual", name="Individual", price=60, sort_order=20)
        self.assertEqual(
            [t.slug for t in MembershipTier.objects.all()],
            ["silver-screen", "individual", "family-plus"],
        )

    def test_benefits_come_back_in_benefit_order(self) -> None:
        """The M2M is plain; the order lives on the benefit."""
        tier = make_tier()
        rentals = make_benefit(name="10% off rentals", sort_order=60)
        matinee = make_benefit(name="$2 off matinee tickets", sort_order=10)
        tier.benefits.add(rentals, matinee)
        self.assertEqual(
            [b.name for b in tier.benefits.all()],
            ["$2 off matinee tickets", "10% off rentals"],
        )
```

- [ ] **Step 4: Run them and watch them fail**

Run: `.venv/bin/python manage.py test audience.tests.test_membership_tier -v 2`
Expected: FAIL — `TypeError` on unexpected keyword `slug`/`sort_order`, and `AttributeError` for `show_on_membership_page`.

- [ ] **Step 5: Write `MembershipBenefit`**

Replace `audience/models/membership_benefit.py` entirely:

```python
from django.db import models


class MembershipBenefit(models.Model):
    """One perk line, shared across every tier that offers it.

    Tiers differ in which *variant* of a perk they carry — "$1 off evening
    tickets" for Silver Screen against "$4 off evening tickets" for the
    rest — so the variants are separate rows sharing a `sort_order`. That
    keeps every tier's perk list in the same category order without a
    per-tier position: matinee, evening, small popcorn, medium & large
    popcorn, birthday, rentals.
    """

    name = models.CharField(
        max_length=255,
        help_text="The perk exactly as it should read on the membership page.",
    )
    description = models.TextField(
        blank=True,
        help_text="Internal detail for staff. Not rendered on the website.",
    )
    sort_order = models.IntegerField(
        default=0,
        help_text="Lower sorts first. Variants of the same perk share a value.",
    )

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Membership benefit"
        verbose_name_plural = "Membership benefits"

    def __str__(self) -> str:
        return self.name
```

- [ ] **Step 6: Write `MembershipTier`**

Replace `audience/models/membership_tier.py` entirely. Field names match
`templates/partials/tier_card.html` exactly, so a tier instance drops into the
template where a catalogue dict used to go:

```python
from django.db import models

from .membership_benefit import MembershipBenefit


class MembershipTier(models.Model):
    """A membership tier as advertised on /membership/.

    Field names deliberately match what templates/partials/tier_card.html
    already reads, so moving the catalogue out of web.constants needed no
    template rewrite.
    """

    slug = models.SlugField(
        unique=True,
        help_text="Square redirects to /thanks?tier=<slug> and the Join button "
        "carries it for analytics. Changing it breaks both — don't.",
    )
    name = models.CharField(max_length=45)
    eyebrow = models.CharField(
        max_length=60,
        blank=True,
        help_text="Small line above the name, e.g. 'Seniors 65+'. "
        "Blank renders 'Patron Card'.",
    )
    description = models.TextField(
        blank=True,
        help_text="Internal detail for staff. Not rendered on the website.",
    )
    price = models.PositiveIntegerField(
        help_text="Whole dollars. The page prints this raw, so 35 renders $35."
    )
    duration_months = models.PositiveSmallIntegerField(default=12)
    featured = models.BooleanField(
        default=False, help_text="Shows the 'Best Value' ribbon."
    )
    is_family_tier = models.BooleanField(
        default=False, help_text="Shows the 'For Families' ribbon."
    )
    checkout_url = models.URLField(blank=True, help_text="The Square payment link.")
    benefits = models.ManyToManyField(MembershipBenefit, blank=True)
    show_on_membership_page = models.BooleanField(
        default=True,
        help_text="Show this tier on the public membership page. Turn off to "
        "retire a tier: it stays in the admin and dashboard, and historical "
        "terms keep pointing at it.",
    )
    sort_order = models.IntegerField(
        default=0, help_text="Lower sorts first on the membership page."
    )

    class Meta:
        ordering = ["sort_order", "price"]
        verbose_name = "Membership tier"
        verbose_name_plural = "Membership tiers"

    def __str__(self) -> str:
        return self.name
```

- [ ] **Step 7: Register both in the admin**

Replace the two admin classes added in the uncommitted work. In `audience/admin.py`, the import line becomes:

```python
from .models import (
    Member,
    MembershipBenefit,
    MembershipTerm,
    MembershipTier,
    Subscriber,
)
```

and the two registrations become (note two blank lines between classes — the
uncommitted version has one, which flake8 rejects as `E302`):

```python
@admin.register(MembershipTier)
class MembershipTierAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "price", "show_on_membership_page", "sort_order")
    list_filter = ("show_on_membership_page", "featured", "is_family_tier")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("benefits",)


@admin.register(MembershipBenefit)
class MembershipBenefitAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    search_fields = ("name",)
```

- [ ] **Step 8: Generate the schema migration**

Run: `.venv/bin/python manage.py makemigrations audience -n membershipbenefit_membershiptier`
Expected: creates `audience/migrations/0003_membershipbenefit_membershiptier.py` creating both models. It must **not** mention `membershipterm` — the FK swap is Task 4.

- [ ] **Step 9: Run the tests**

Run: `.venv/bin/python manage.py test audience -v 2`
Expected: PASS, including the 11 new tests.

- [ ] **Step 10: Lint and commit**

Run: `.venv/bin/python -m flake8 audience`
Expected: no output.

```bash
git add audience
git commit -m "feat(audience): membership tier and benefit catalogue models

Fields are named to match templates/partials/tier_card.html so a tier
instance substitutes for the web.constants dict without a template
rewrite. Benefits carry a shared sort_order, which keeps every tier's
perk list in category order from a plain ManyToManyField.

Replaces the two unapplied migrations from the initial sketch.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 3: Seed the five tiers and ten benefits

A data migration carrying its own literal copy of the catalogue. `audience` cannot import `web`, and a migration that imports application code breaks when that code changes — which this one does, in Task 7.

**Files:**
- Create: `audience/migrations/0004_seed_membership_catalogue.py`
- Test: `audience/tests/test_membership_catalogue_seed.py`

**Interfaces:**
- Consumes: `MembershipTier`, `MembershipBenefit` (Task 2).
- Produces: five seeded tiers and ten seeded benefits present in every test database.

- [ ] **Step 1: Write the failing test**

Create `audience/tests/test_membership_catalogue_seed.py`:

```python
"""The seed migration's output.

Django runs every migration to build the test database, so the seeded rows
are simply present — no migration-executor harness needed.
"""

from django.test import TestCase

from audience.models import MembershipBenefit, MembershipTier

EXPECTED = {
    "silver-screen": (35, "Seniors 65+", False, False),
    "individual": (60, "", False, False),
    "cinema-supporter": (120, "", True, False),
    "family": (150, "", False, True),
    "family-plus": (250, "", False, True),
}


class SeededCatalogueTests(TestCase):
    def test_five_tiers(self) -> None:
        self.assertEqual(MembershipTier.objects.count(), 5)

    def test_ten_benefits(self) -> None:
        self.assertEqual(MembershipBenefit.objects.count(), 10)

    def test_tier_fields(self) -> None:
        for slug, (price, eyebrow, featured, family) in EXPECTED.items():
            tier = MembershipTier.objects.get(slug=slug)
            self.assertEqual(tier.price, price, slug)
            self.assertEqual(tier.eyebrow, eyebrow, slug)
            self.assertEqual(tier.featured, featured, slug)
            self.assertEqual(tier.is_family_tier, family, slug)
            self.assertEqual(tier.duration_months, 12, slug)
            self.assertTrue(tier.show_on_membership_page, slug)
            self.assertTrue(tier.checkout_url.startswith("https://square.link/"), slug)

    def test_tiers_sort_by_price(self) -> None:
        self.assertEqual(
            [t.slug for t in MembershipTier.objects.all()],
            ["silver-screen", "individual", "cinema-supporter", "family",
             "family-plus"],
        )

    def test_silver_screen_perks(self) -> None:
        """The tier whose perks differ from every other one."""
        tier = MembershipTier.objects.get(slug="silver-screen")
        self.assertEqual(
            [b.name for b in tier.benefits.all()],
            [
                "$2 off matinee tickets",
                "$1 off evening tickets",
                "$1 off small popcorn",
                "$1 off medium & large popcorn",
                "Free small popcorn during your birthday month",
                "10% off rentals",
            ],
        )

    def test_family_plus_perks(self) -> None:
        tier = MembershipTier.objects.get(slug="family-plus")
        self.assertEqual(
            [b.name for b in tier.benefits.all()],
            [
                "$2 off matinee tickets",
                "$4 off evening tickets",
                "$1 off small popcorn",
                "$2 off medium & large popcorn",
                "Free small popcorn during your birthday month",
                "20% off rentals & parties",
            ],
        )

    def test_every_tier_has_six_perks(self) -> None:
        for tier in MembershipTier.objects.all():
            self.assertEqual(tier.benefits.count(), 6, tier.slug)

    def test_benefits_are_shared_not_duplicated(self) -> None:
        """Ten rows for thirty tier-perk pairings is the point of the M2M."""
        matinee = MembershipBenefit.objects.get(name="$2 off matinee tickets")
        self.assertEqual(matinee.membershiptier_set.count(), 5)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python manage.py test audience.tests.test_membership_catalogue_seed -v 2`
Expected: FAIL — `MembershipTier.objects.count()` is 0, nothing is seeded yet.

- [ ] **Step 3: Write the seed migration**

Create `audience/migrations/0004_seed_membership_catalogue.py`:

```python
"""Seed the tier catalogue from what web.constants.MEMBERSHIP held.

The data is copied in rather than imported: `audience` must never import
`web` (web imports audience), and the constant is deleted later in this
same piece of work. A migration that reaches into application code stops
being reproducible the moment that code moves.
"""

from django.db import migrations

# name -> sort_order. Variants of a category share a value, which is what
# keeps every tier's perk list in the same order.
BENEFITS = [
    ("$2 off matinee tickets", 10),
    ("$1 off evening tickets", 20),
    ("$4 off evening tickets", 20),
    ("$1 off small popcorn", 30),
    ("$1 off medium & large popcorn", 40),
    ("$2 off medium & large popcorn", 40),
    ("Free small popcorn during your birthday month", 50),
    ("10% off rentals", 60),
    ("15% off rentals & parties", 60),
    ("20% off rentals & parties", 60),
]

COMMON = [
    "$2 off matinee tickets",
    "$4 off evening tickets",
    "$1 off small popcorn",
    "$2 off medium & large popcorn",
    "Free small popcorn during your birthday month",
]

TIERS = [
    {
        "slug": "silver-screen",
        "name": "Silver Screen",
        "eyebrow": "Seniors 65+",
        "price": 35,
        "featured": False,
        "is_family_tier": False,
        "checkout_url": "https://square.link/u/UnQLNeHp",
        "sort_order": 10,
        "benefits": [
            "$2 off matinee tickets",
            "$1 off evening tickets",
            "$1 off small popcorn",
            "$1 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "10% off rentals",
        ],
    },
    {
        "slug": "individual",
        "name": "Individual",
        "eyebrow": "",
        "price": 60,
        "featured": False,
        "is_family_tier": False,
        "checkout_url": "https://square.link/u/zricPsRR",
        "sort_order": 20,
        "benefits": COMMON + ["10% off rentals"],
    },
    {
        "slug": "cinema-supporter",
        "name": "Cinema Supporter",
        "eyebrow": "",
        "price": 120,
        "featured": True,
        "is_family_tier": False,
        "checkout_url": "https://square.link/u/2HnpAb9N",
        "sort_order": 30,
        "benefits": COMMON + ["15% off rentals & parties"],
    },
    {
        "slug": "family",
        "name": "Family",
        "eyebrow": "",
        "price": 150,
        "featured": False,
        "is_family_tier": True,
        "checkout_url": "https://square.link/u/FkcUasKu",
        "sort_order": 40,
        "benefits": COMMON + ["15% off rentals & parties"],
    },
    {
        "slug": "family-plus",
        "name": "Family Plus",
        "eyebrow": "",
        "price": 250,
        "featured": False,
        "is_family_tier": True,
        "checkout_url": "https://square.link/u/1YSgMFSQ",
        "sort_order": 50,
        "benefits": COMMON + ["20% off rentals & parties"],
    },
]


def seed(apps, schema_editor):
    Benefit = apps.get_model("audience", "MembershipBenefit")
    Tier = apps.get_model("audience", "MembershipTier")

    by_name = {}
    for name, sort_order in BENEFITS:
        by_name[name] = Benefit.objects.create(name=name, sort_order=sort_order)

    for spec in TIERS:
        # Copy rather than pop: TIERS is module-level, and popping would
        # mutate it for the life of the process. A reverse followed by a
        # re-apply — which `migrate` back and forward in one process does —
        # would then fail on the missing key.
        fields = {k: v for k, v in spec.items() if k != "benefits"}
        tier = Tier.objects.create(**fields)
        tier.benefits.set([by_name[n] for n in spec["benefits"]])


def unseed(apps, schema_editor):
    apps.get_model("audience", "MembershipTier").objects.all().delete()
    apps.get_model("audience", "MembershipBenefit").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("audience", "0003_membershipbenefit_membershiptier"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python manage.py test audience -v 2`
Expected: PASS, including the 8 new seed tests.

- [ ] **Step 5: Confirm no stray migrations**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: exit 0, "No changes detected".

- [ ] **Step 6: Lint and commit**

Run: `.venv/bin/python -m flake8 audience`
Expected: no output. (Migrations are excluded from flake8, but the test file is not.)

```bash
git add audience
git commit -m "feat(audience): seed the tier catalogue

Five tiers and ten shared benefits, carrying the data web.constants held.
Copied into the migration rather than imported: audience must never import
web, and the constant is deleted shortly.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 4: `MembershipTerm.tier` becomes a foreign key

The four-step swap. Production almost certainly has zero `MembershipTerm` rows — `audience.0002` is on `origin/main` but undeployed — but membership terms are revenue records, so the migration copies data across rather than trusting that.

This task also updates every test that assigns a slug string to `tier`, because the field stops accepting one.

**Files:**
- Modify: `audience/models/membership_term.py`
- Create: `audience/migrations/0005_membershipterm_tier_fk.py`
- Modify: `audience/tests/test_member.py`
- Test: `audience/tests/test_membership_tier.py` (append)

**Interfaces:**
- Consumes: `MembershipTier` (Task 2), seeded rows (Task 3).
- Produces: `MembershipTerm.tier` as `ForeignKey(MembershipTier, on_delete=PROTECT, related_name="terms")`.

- [ ] **Step 1: Write the failing test**

Append to `audience/tests/test_membership_tier.py`:

```python
class TierDeletionTests(TestCase):
    """Membership terms are revenue records. Retire tiers; never delete them."""

    def test_deleting_a_tier_with_terms_is_refused(self) -> None:
        import datetime

        from decimal import Decimal

        from django.db.models import ProtectedError

        from audience.models import Member, MembershipTerm

        tier = MembershipTier.objects.get(slug="individual")
        member = Member.objects.create(
            first_name="Ada", last_name="Byron", email="ada@example.com"
        )
        MembershipTerm.objects.create(
            member=member,
            tier=tier,
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("60.00"),
        )
        with self.assertRaises(ProtectedError):
            tier.delete()

    def test_a_tier_with_no_terms_can_still_be_deleted(self) -> None:
        tier = MembershipTier.objects.create(
            slug="typo-tier", name="Typo", price=1
        )
        tier.delete()
        self.assertFalse(MembershipTier.objects.filter(slug="typo-tier").exists())

    def test_retiring_keeps_the_tier_and_its_terms(self) -> None:
        tier = MembershipTier.objects.get(slug="individual")
        tier.show_on_membership_page = False
        tier.save(update_fields=["show_on_membership_page"])
        tier.refresh_from_db()
        self.assertTrue(MembershipTier.objects.filter(slug="individual").exists())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python manage.py test audience.tests.test_membership_tier.TierDeletionTests -v 2`
Expected: FAIL — `ValueError: Cannot assign "<MembershipTier: Individual>": "MembershipTerm.tier" must be a string`, or similar, because `tier` is still a `CharField`.

- [ ] **Step 3: Change the field**

In `audience/models/membership_term.py`, replace the `tier` field and its stale comment (the comment describes the slug arrangement this task removes), and restore the blank line the uncommitted edit deleted above `class MembershipTerm`:

```python
    tier = models.ForeignKey(
        "audience.MembershipTier",
        related_name="terms",
        on_delete=models.PROTECT,
        help_text="Retire a tier with show_on_membership_page instead of "
        "deleting it — terms are revenue records.",
    )
```

Make sure there are **two** blank lines between the `add_months` import and `class MembershipTerm`.

- [ ] **Step 4: Write the migration by hand**

`makemigrations` would emit a single destructive `AlterField`. Create
`audience/migrations/0005_membershipterm_tier_fk.py` instead:

```python
"""Turn MembershipTerm.tier from a slug string into a foreign key.

Four steps rather than one AlterField, which would cast varchar to integer
and drop every value it could not convert. Membership terms carry
price_paid; they are revenue records, not scratch data.
"""

import django.db.models.deletion
from django.db import migrations, models


def slug_to_fk(apps, schema_editor):
    Term = apps.get_model("audience", "MembershipTerm")
    Tier = apps.get_model("audience", "MembershipTier")
    by_slug = {t.slug: t for t in Tier.objects.all()}

    for term in Term.objects.exclude(tier="").iterator():
        tier = by_slug.get(term.tier)
        if tier is None:
            raise RuntimeError(
                f"MembershipTerm {term.pk} has tier {term.tier!r}, which matches "
                f"no MembershipTier. Refusing to guess. Known slugs: "
                f"{sorted(by_slug)}"
            )
        term.tier_fk = tier
        term.save(update_fields=["tier_fk"])


def fk_to_slug(apps, schema_editor):
    Term = apps.get_model("audience", "MembershipTerm")
    for term in Term.objects.select_related("tier_fk").iterator():
        term.tier = term.tier_fk.slug if term.tier_fk else ""
        term.save(update_fields=["tier"])


class Migration(migrations.Migration):

    dependencies = [
        ("audience", "0004_seed_membership_catalogue"),
    ]

    operations = [
        migrations.AddField(
            model_name="membershipterm",
            name="tier_fk",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="terms",
                to="audience.membershiptier",
            ),
        ),
        migrations.RunPython(slug_to_fk, fk_to_slug),
        migrations.RemoveField(model_name="membershipterm", name="tier"),
        migrations.RenameField(
            model_name="membershipterm", old_name="tier_fk", new_name="tier"
        ),
        migrations.AlterField(
            model_name="membershipterm",
            name="tier",
            field=models.ForeignKey(
                help_text="Retire a tier with show_on_membership_page instead "
                "of deleting it — terms are revenue records.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="terms",
                to="audience.membershiptier",
            ),
        ),
    ]
```

- [ ] **Step 5: Update the existing term tests**

`audience/tests/test_member.py` creates terms with `tier="individual"`. Replace every such assignment with a tier instance. At the top of the file add:

```python
from audience.models import MembershipTier
```

and wherever a term is created, resolve the tier first:

```python
tier = MembershipTier.objects.get(slug="individual")
```

then pass `tier=tier`. The seeded rows from Task 3 are available in every test.

Run `grep -n 'tier=' audience/tests/test_member.py` to find every site; fix them all.

- [ ] **Step 6: Run the audience tests**

Run: `.venv/bin/python manage.py test audience -v 2`
Expected: PASS. `dashboard` is still broken at this point — that is Task 5.

- [ ] **Step 7: Confirm the migration is complete**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: exit 0, "No changes detected". If Django wants another migration, the hand-written one does not match the model — reconcile before moving on.

- [ ] **Step 8: Lint and commit**

Run: `.venv/bin/python -m flake8 audience`
Expected: no output.

```bash
git add audience
git commit -m "feat(audience): MembershipTerm.tier becomes a protected foreign key

Four migration steps rather than one AlterField: a varchar-to-integer cast
would drop every tier it could not convert, and terms carry price_paid.

PROTECT, not CASCADE — deleting a tier must never take the membership
terms sold under it. show_on_membership_page is the retire path.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 5: Port the dashboard

The FK broke the roster. This restores it: the term form becomes a `ModelChoiceField`, the `tier_labels` dictionary disappears because `term.tier.name` is now reachable directly, and the CSV keeps emitting slugs.

**Files:**
- Modify: `dashboard/forms.py:5` (imports), `:93` (choices), `:116-119` (field), `:150-160` (clean)
- Modify: `dashboard/member_views.py:18`, `:68`, `:88`, `:167`, `:194`, and the CSV writer
- Modify: `dashboard/templates/dashboard/_member_list.html:15`
- Modify: `dashboard/templates/dashboard/_term_list.html:12`
- Modify: `dashboard/tests/test_member_terms.py`, `dashboard/tests/test_members.py`

**Interfaces:**
- Consumes: `MembershipTerm.tier` as an FK (Task 4).
- Produces: no new names; `MEMBERSHIP_TIER_CHOICES` is removed.

- [ ] **Step 1: Update the form**

In `dashboard/forms.py`, the import on line 5 becomes:

```python
from audience.models import Member, MembershipTerm, MembershipTier
```

Delete `MEMBERSHIP_TIER_CHOICES` and its comment entirely (the comment explains the slug arrangement that no longer exists). Remove `MEMBERSHIP` and `MEMBERSHIP_BY_SLUG` from the `web.constants` import; if that leaves the import empty, delete the line.

Replace the `tier` field declaration on `MembershipTermForm`:

```python
    tier = forms.ModelChoiceField(
        queryset=MembershipTier.objects.all(),
        empty_label=None,
        widget=forms.Select(attrs={"class": "input"}),
    )
```

In `__init__`, narrow the queryset to listed tiers while keeping whichever tier
the term already uses, so editing a term on a retired tier does not silently
move it:

```python
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Both are filled from the tier when left blank, so staff can add a
        # renewal by choosing a tier and a start date and nothing else.
        self.fields["expires_on"].required = False
        self.fields["price_paid"].required = False

        # Retired tiers stay selectable on a term that already uses one,
        # so editing an old record cannot quietly re-tier it.
        listed = Q(show_on_membership_page=True)
        if self.instance.pk and self.instance.tier_id:
            listed |= Q(pk=self.instance.tier_id)
        self.fields["tier"].queryset = MembershipTier.objects.filter(listed)
```

That needs `from django.db.models import Q` at the top of `dashboard/forms.py`.
Import `Q` by name rather than `from django.db import models` — this module
already imports model classes from `audience.models` and `cinema.models`, so a
bare `models` name here would read as one of those.

Replace the `clean()` body's tier lookup — `cleaned.get("tier")` is now a
`MembershipTier` instance, so the `MEMBERSHIP_BY_SLUG` hop disappears:

```python
    def clean(self):
        cleaned = super().clean()
        tier = cleaned.get("tier")
        started_on = cleaned.get("started_on")
        if tier is None:
            return cleaned

        if started_on and not cleaned.get("expires_on"):
            cleaned["expires_on"] = add_months(started_on, tier.duration_months)
        if cleaned.get("price_paid") is None:
            cleaned["price_paid"] = tier.price

        expires_on = cleaned.get("expires_on")
        if started_on and expires_on and expires_on < started_on:
            self.add_error("expires_on", "Expiry cannot be before the start date.")
        return cleaned
```

- [ ] **Step 2: Drop `tier_labels` from the views**

In `dashboard/member_views.py`, delete the import on line 18
(`from web.constants import MEMBERSHIP_TIER_LABELS`) and remove the
`"tier_labels": MEMBERSHIP_TIER_LABELS,` entry from all four render contexts
(lines ~68, ~88, ~167, ~194).

In `MemberExportView`, the CSV must keep writing slugs so the column does not
change shape. Replace the `term.tier` cell:

```python
                term.tier.slug if term else "",
```

- [ ] **Step 3: Update the two templates**

`dashboard/templates/dashboard/_member_list.html:15` becomes:

```html
          <td>{% if member.current_term %}{{ member.current_term.tier.name }}{% else %}—{% endif %}</td>
```

`dashboard/templates/dashboard/_term_list.html:12` becomes:

```html
          <td>{{ term.tier.name }}</td>
```

If `get_item` is now unused across the dashboard templates, leave the filter in
place — it is a general-purpose helper and other pages may want it. Check with
`grep -rn get_item dashboard/templates/` and only remove the `{% load %}` from
files that no longer use it.

- [ ] **Step 4: Update the dashboard tests**

`dashboard/tests/test_member_terms.py` and `dashboard/tests/test_members.py` post
`tier` as a form value and create terms directly. Form posts must now send a
tier **primary key**, and direct creates must pass an instance.

Find every site: `grep -n 'tier' dashboard/tests/test_member_terms.py dashboard/tests/test_members.py`

In each file add a helper near the existing `give_term`:

```python
def a_tier(slug="individual"):
    return MembershipTier.objects.get(slug=slug)
```

with `from audience.models import MembershipTier` at the top. Then:
- `MembershipTerm.objects.create(..., tier="individual", ...)` → `tier=a_tier()`
- `self.client.post(url, {"tier": "individual", ...})` → `{"tier": a_tier().pk, ...}`
- `give_term(member, tier="cinema-supporter")` → `give_term(member, tier=a_tier("cinema-supporter"))`, and update `give_term`'s own default the same way.

The CSV test `test_one_row_per_member_from_the_latest_term` asserts
`assertIn("cinema-supporter", rows[1])` — that still holds, because the export
writes slugs.

- [ ] **Step 5: Test the tier dropdown**

The queryset narrowing in Step 1 is new behaviour and needs its own cover.
Append to `dashboard/tests/test_member_terms.py`:

```python
class TermFormTierChoicesTests(TestCase):
    """The dropdown comes from the database, and retiring is not destructive."""

    def test_choices_come_from_the_catalogue(self) -> None:
        from dashboard.forms import MembershipTermForm

        slugs = {t.slug for t in MembershipTermForm().fields["tier"].queryset}
        self.assertEqual(
            slugs,
            {"silver-screen", "individual", "cinema-supporter", "family",
             "family-plus"},
        )

    def test_retired_tier_drops_out_for_a_new_term(self) -> None:
        from dashboard.forms import MembershipTermForm

        tier = MembershipTier.objects.get(slug="family-plus")
        tier.show_on_membership_page = False
        tier.save(update_fields=["show_on_membership_page"])

        slugs = {t.slug for t in MembershipTermForm().fields["tier"].queryset}
        self.assertNotIn("family-plus", slugs)

    def test_retired_tier_stays_selectable_on_a_term_that_uses_it(self) -> None:
        """Editing an old record must not quietly re-tier it."""
        import datetime
        from decimal import Decimal

        from dashboard.forms import MembershipTermForm

        tier = MembershipTier.objects.get(slug="family-plus")
        member = make_member()
        term = MembershipTerm.objects.create(
            member=member, tier=tier,
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("250.00"),
        )
        tier.show_on_membership_page = False
        tier.save(update_fields=["show_on_membership_page"])

        form = MembershipTermForm(instance=term)
        self.assertIn(tier, form.fields["tier"].queryset)

    def test_expiry_defaults_from_the_selected_tier(self) -> None:
        import datetime

        from dashboard.forms import MembershipTermForm

        form = MembershipTermForm(data={
            "tier": a_tier("individual").pk,
            "started_on": "2026-03-01",
        })
        self.assertTrue(form.is_valid(), form.errors)
        # 12 months, inclusive-through semantics preserved by add_months.
        self.assertEqual(
            form.cleaned_data["expires_on"],
            datetime.date(2027, 3, 1),
        )

    def test_price_defaults_from_the_selected_tier(self) -> None:
        from dashboard.forms import MembershipTermForm

        form = MembershipTermForm(data={
            "tier": a_tier("cinema-supporter").pk,
            "started_on": "2026-03-01",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price_paid"], 120)
```

`make_member` already exists in that module; reuse it rather than defining
another. `add_months(date(2026, 3, 1), 12)` returns `date(2027, 3, 1)` —
verified against `audience/dates.py`, which clamps to the target month's length.

- [ ] **Step 6: Run the dashboard tests**

Run: `.venv/bin/python manage.py test dashboard -v 2`
Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run: `.venv/bin/python manage.py test`
Expected: PASS. `web` still renders from the constant and is untouched so far.

- [ ] **Step 8: Lint and commit**

Run: `.venv/bin/python -m flake8 audience dashboard/forms.py dashboard/member_views.py dashboard/tests/test_members.py dashboard/tests/test_member_terms.py`
Expected: no output.

```bash
git add dashboard audience
git commit -m "refactor(dashboard): read tiers through the foreign key

The term form becomes a ModelChoiceField and the tier_labels lookup
dictionary disappears — term.tier.name is reachable directly now. A
retired tier stays selectable on a term that already uses it, so editing
an old record cannot quietly re-tier it.

The CSV keeps emitting slugs, so the column is unchanged.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 6: Point the public page at the database

Where Task 1's characterization test earns its keep: it must pass, unchanged, after this.

**Files:**
- Modify: `web/views.py` (`MembershipView`, `ThanksView`, imports)
- Modify: `templates/partials/tier_card.html` (perk loop only)
- Test: `web/tests/test_membership_catalogue.py` (append)

**Interfaces:**
- Consumes: `MembershipTier` with seeded rows.
- Produces: no new names.

- [ ] **Step 1: Write the failing test**

Append to `web/tests/test_membership_catalogue.py`:

```python
class RetiredTierTests(TestCase):
    """show_on_membership_page is a website switch, nothing more."""

    def retire(self, slug="family-plus"):
        from audience.models import MembershipTier

        tier = MembershipTier.objects.get(slug=slug)
        tier.show_on_membership_page = False
        tier.save(update_fields=["show_on_membership_page"])
        return tier

    def test_retired_tier_is_absent_from_the_page(self) -> None:
        self.retire()
        html = self.client.get(reverse("membership")).content.decode()
        self.assertNotIn('data-track-tier="family-plus"', html)
        self.assertNotIn("https://square.link/u/1YSgMFSQ", html)

    def test_the_other_tiers_still_render(self) -> None:
        self.retire()
        html = self.client.get(reverse("membership")).content.decode()
        for slug in ("silver-screen", "individual", "cinema-supporter", "family"):
            self.assertIn(f'data-track-tier="{slug}"', html)

    def test_retired_tier_still_resolves_on_thanks(self) -> None:
        """A bookmarked Square link must still attribute its revenue."""
        self.retire()
        html = self.client.get("/thanks", {"tier": "family-plus"}).content.decode()
        self.assertIn("'purchase'", html)
        self.assertIn("value: 250", html)


class ThanksValueSourceTests(TestCase):
    def test_value_comes_from_the_database_not_the_query_string(self) -> None:
        html = self.client.get(
            "/thanks", {"tier": "individual", "value": "99999"}
        ).content.decode()
        self.assertIn("value: 60", html)
        self.assertNotIn("99999", html)

    def test_unknown_tier_fires_nothing(self) -> None:
        html = self.client.get("/thanks", {"tier": "not-a-tier"}).content.decode()
        self.assertNotIn("'purchase'", html)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python manage.py test web.tests.test_membership_catalogue.RetiredTierTests -v 2`
Expected: FAIL — the retired tier still renders, because the page reads the constant.

- [ ] **Step 3: Rewrite the two views**

In `web/views.py`, add the model import alongside the existing `audience` imports:

```python
from audience.models import MembershipTier
```

Remove `MEMBERSHIP` from the `web.constants` import list, keeping `MEMBERSHIP_FAQ`.

`MembershipView.get_context_data` becomes:

```python
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tiers"] = (
            MembershipTier.objects.filter(show_on_membership_page=True)
            .prefetch_related("benefits")
        )
        ctx["faqs"] = MEMBERSHIP_FAQ
        return ctx
```

`ThanksView.get_context_data` becomes — note **no** visibility filter, so a
bookmarked link to a retired tier still attributes:

```python
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        slug = self.request.GET.get("tier", "")
        ctx["tier"] = MembershipTier.objects.filter(slug=slug).first()
        return ctx
```

Update the `ThanksView` docstring: the sentence "The value is looked up
server-side from MEMBERSHIP by slug" becomes "The value is looked up server-side
from the tier record by slug". The property it describes — never trusting the
query string — is unchanged and still tested.

- [ ] **Step 4: Update the perk loop**

`templates/partials/tier_card.html` is the only template that changes, and only
in three places. `{% if tier.perks %}` becomes `{% if tier.benefits.all %}`,
`{% for perk in tier.perks %}` becomes `{% for perk in tier.benefits.all %}`, and
`{{ perk }}` becomes `{{ perk.name }}`.

Every other line — the ribbons, eyebrow, name, price, duration and Join link —
is untouched, because the model fields are named to match.

- [ ] **Step 5: Run the characterization test**

Run: `.venv/bin/python manage.py test web.tests.test_membership_catalogue -v 2`
Expected: PASS — all of it, including the 8 tests written in Task 1 **unmodified**. If any Task 1 test now fails, the page changed and the refactor is wrong. Fix the code, never the Task 1 expectations.

- [ ] **Step 6: Lint and commit**

Run: `.venv/bin/python -m flake8 web`
Expected: `web/constants.py` still reports its pre-existing `E501`s on lines 152–168; no other output. Those lines belong to `MEMBERSHIP_FAQ` and are not this plan's to fix.

```bash
git add web templates/partials/tier_card.html
git commit -m "refactor(web): render the membership page from the database

MembershipView and ThanksView read MembershipTier instead of the
constant. The card partial needed three edits — the perk loop — because
the model fields are named for what the template already read.

/thanks deliberately does not filter on show_on_membership_page: a
bookmarked Square link for a retired tier must still attribute.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 7: Delete the constant

Nothing reads `MEMBERSHIP` now except the analytics tests. Porting those and deleting the constant is what makes the database the single catalogue rather than the first of two.

**Files:**
- Modify: `web/constants.py` (delete `MEMBERSHIP`, `MEMBERSHIP_BY_SLUG`, `MEMBERSHIP_TIER_LABELS`)
- Modify: `web/tests/test_analytics.py`

**Interfaces:**
- Consumes: everything above.
- Produces: a repo with one tier catalogue.

- [ ] **Step 1: Port the analytics tests**

`web/tests/test_analytics.py` imports `MEMBERSHIP` and iterates it. Replace the
import with `from audience.models import MembershipTier`, then:

`test_membership_join_buttons_tagged_with_tier` becomes:

```python
    def test_membership_join_buttons_tagged_with_tier(self):
        html = self.client.get(reverse("membership")).content.decode()
        tiers = MembershipTier.objects.filter(show_on_membership_page=True)
        hits = tracked(html, "membership_join_click")
        self.assertEqual(len(hits), tiers.count())
        for tier in tiers:
            self.assertIn(f'data-track-tier="{tier.slug}"', html)
```

`ThanksPageTests.tier` becomes:

```python
    def tier(self, slug):
        return MembershipTier.objects.get(slug=slug)
```

and its three callers change `tier["slug"]` to `tier.slug` and `tier['price']` to
`tier.price`. The docstring on `test_value_comes_from_constants_not_the_query_string`
says "constants"; rename the method to
`test_value_comes_from_the_record_not_the_query_string` and keep the docstring
"Revenue must not be forgeable by editing the URL."

- [ ] **Step 2: Run the analytics tests**

Run: `.venv/bin/python manage.py test web.tests.test_analytics -v 2`
Expected: PASS.

- [ ] **Step 3: Confirm nothing else reads the constant**

Run: `grep -rn "MEMBERSHIP\b\|MEMBERSHIP_BY_SLUG\|MEMBERSHIP_TIER_LABELS" --include="*.py" --include="*.html" . | grep -v "\.venv/" | grep -v MEMBERSHIP_FAQ`
Expected: only the definitions in `web/constants.py`. Anything else is a missed consumer — port it before continuing.

- [ ] **Step 4: Delete the constant**

In `web/constants.py`, delete the whole `MEMBERSHIP = [...]` list and the two
derived dictionaries `MEMBERSHIP_BY_SLUG` and `MEMBERSHIP_TIER_LABELS`.

Leave `MEMBERSHIP_FAQ` and its "Ported verbatim from the React SPA" comment
exactly as they are — the FAQ is prose, not catalogue data.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python manage.py test`
Expected: PASS, no failures and no errors. Report the exact counts.

- [ ] **Step 6: Confirm no stray migrations**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: exit 0, "No changes detected".

- [ ] **Step 7: Lint everything this plan touched**

Run: `.venv/bin/python -m flake8 audience dashboard/forms.py dashboard/member_views.py web`
Expected: no output. The `web/constants.py` `E501`s from Task 6 are gone with the
lines that carried them — the remaining FAQ lines are within the limit. If any
`E501` survives in `MEMBERSHIP_FAQ`, leave it; it predates this work.

- [ ] **Step 8: Commit**

```bash
git add web
git commit -m "refactor(web): delete the MEMBERSHIP constant

The database is the catalogue now. Changing a price or a perk is an admin
edit rather than a deploy.

MEMBERSHIP_FAQ stays — it is prose, not catalogue data.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

## Deployment

`manage.py migrate` and nothing else. No environment variables, no Square
reconfiguration, no `collectstatic` dependency — no static file changes.

**Sequencing constraint, and it matters:** this must reach production in the same
deploy as `audience.0002`, or at least before anyone types members into the roster.
Migration 0005 copies each term's tier slug onto a foreign key and **raises** if a
slug matches no seeded tier, so a mismatch fails the deploy loudly instead of
silently dropping tier data. That is the desired behaviour, but it means a
half-populated roster with a hand-typed tier slug would block the deploy until
someone reconciles it.

The local database is stale sqlite, not production. Nothing here can be verified
against real membership data before deploy; Task 1's characterization test is the
substitute.
