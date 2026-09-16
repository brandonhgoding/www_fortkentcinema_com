# Free Admissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each membership tier a monthly free-admission allowance, and record every redemption, so staff can answer "has this member used this month's?" and "how many did we give away?".

**Architecture:** One field on `MembershipTier` for the allowance, one new `FreeAdmission` row per redemption. Usage is never stored — the roster counts it in SQL with an annotation, the detail page counts it in Python through a helper, and both mean the same calendar month. Going over the allowance is a policy the UI warns about, never a database constraint.

**Tech Stack:** Django 5.2.3, htmx + Alpine (already wired into `base_dashboard.html`), Django templates, `manage.py test` + `flake8`.

**Spec:** `docs/superpowers/specs/2026-09-15-free-admissions-design.md`

## Global Constraints

- **Python is `.venv/bin/python`.** There is no bare `python` on this machine. Every command runs from the repo root.
- **Tests:** `.venv/bin/python manage.py test <label> -v 2`. Full suite: `.venv/bin/python manage.py test`.
- **Lint:** `.venv/bin/python -m flake8 <paths>` — `max-line-length = 88`, migrations excluded from lint. mypy is configured but cannot run in this checkout; do not attempt it. black is configured but unapplied; do not reformat files you did not write.
- **`dashboard/` and `web/` carry pre-existing flake8 debt** in files this plan does not own (`dashboard/views.py`, `dashboard/urls.py`, `dashboard/forms.py`'s `ScreenForm`/`EngagementForm`, `dashboard/tests/test_engagements.py`, `web/constants.py`'s FAQ lines). Lint only the paths each task names. Never "fix" a file you do not own.
- **`audience` must never import `web`.** `web/views.py` imports `audience.models`, so the reverse is circular.
- **The allowance is a policy, not an invariant.** No unique constraint, no check constraint, no validation that refuses a redemption. Staff may always exceed it.
- **Months are calendar months.** The allowance resets on the 1st. Unused admissions do not carry over.
- **The five tier allowances are fixed:** Silver Screen 0, Individual 0, Cinema Supporter 1, Family 0, Family Plus 4.
- **Every view is staff-only** via `StaffRequiredMixin` from `dashboard/mixins.py`.
- **Migrations are already at `audience.0005`.** This plan adds 0006, 0007 and 0008 in that order.

---

### Task 1: The per-tier allowance

**Files:**
- Modify: `audience/models/membership_tier.py`
- Modify: `audience/admin.py`
- Create: `audience/migrations/0006_membershiptier_free_admissions_per_month.py` (generated)
- Create: `audience/migrations/0007_seed_free_admission_allowances.py` (hand-written)
- Test: `audience/tests/test_membership_tier.py` (append)

**Interfaces:**
- Produces: `MembershipTier.free_admissions_per_month` (`PositiveSmallIntegerField`, default 0), seeded to 1 for `cinema-supporter` and 4 for `family-plus`.

- [ ] **Step 1: Write the failing tests**

Append to `audience/tests/test_membership_tier.py`:

```python
class FreeAdmissionAllowanceTests(TestCase):
    """The per-tier monthly allowance, as seeded."""

    def test_defaults_to_none_for_a_new_tier(self) -> None:
        tier = MembershipTier.objects.create(
            slug="brand-new", name="Brand New", price=10
        )
        self.assertEqual(tier.free_admissions_per_month, 0)

    def test_seeded_allowances(self) -> None:
        expected = {
            "silver-screen": 0,
            "individual": 0,
            "cinema-supporter": 1,
            "family": 0,
            "family-plus": 4,
        }
        actual = {
            t.slug: t.free_admissions_per_month
            for t in MembershipTier.objects.all()
        }
        self.assertEqual(actual, expected)

    def test_only_two_tiers_grant_any(self) -> None:
        """Most rows on the roster will show no allowance at all."""
        granting = MembershipTier.objects.filter(
            free_admissions_per_month__gt=0
        ).order_by("slug")
        self.assertEqual(
            [t.slug for t in granting], ["cinema-supporter", "family-plus"]
        )
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test audience.tests.test_membership_tier.FreeAdmissionAllowanceTests -v 2`
Expected: FAIL — `TypeError`/`AttributeError`, the field does not exist.

- [ ] **Step 3: Add the field**

In `audience/models/membership_tier.py`, after `duration_months`:

```python
    free_admissions_per_month = models.PositiveSmallIntegerField(
        default=0,
        help_text="Free admissions this tier includes each calendar month. "
        "0 means none. Resets on the 1st; unused ones do not carry over.",
    )
```

- [ ] **Step 4: Show it in the admin**

In `audience/admin.py`, `MembershipTierAdmin.list_display` becomes:

```python
    list_display = (
        "name",
        "slug",
        "price",
        "free_admissions_per_month",
        "show_on_membership_page",
        "sort_order",
    )
```

Leave `get_readonly_fields` and `get_prepopulated_fields` exactly as they are — they
must keep agreeing about `slug`, and this field is not involved.

- [ ] **Step 5: Generate the schema migration**

Run: `.venv/bin/python manage.py makemigrations audience -n membershiptier_free_admissions_per_month`
Expected: creates `audience/migrations/0006_membershiptier_free_admissions_per_month.py` with a single `AddField`. It must mention no other model.

- [ ] **Step 6: Write the seed migration**

Create `audience/migrations/0007_seed_free_admission_allowances.py`:

```python
"""Set the monthly free-admission allowance on the two tiers that grant one.

Confirmed 2026-09-15: only Cinema Supporter (1) and Family Plus (4). The
other three keep the field's default of 0.

Written as an update rather than folded into 0004's seed because 0004 has
already run everywhere this ships; a tier's allowance is editable in the
admin afterwards, so this sets a starting point rather than a truth.
"""

from django.db import migrations

ALLOWANCES = {
    "cinema-supporter": 1,
    "family-plus": 4,
}


def set_allowances(apps, schema_editor):
    Tier = apps.get_model("audience", "MembershipTier")
    for slug, allowance in ALLOWANCES.items():
        Tier.objects.filter(slug=slug).update(
            free_admissions_per_month=allowance
        )


def clear_allowances(apps, schema_editor):
    Tier = apps.get_model("audience", "MembershipTier")
    Tier.objects.filter(slug__in=ALLOWANCES).update(
        free_admissions_per_month=0
    )


class Migration(migrations.Migration):

    dependencies = [
        ("audience", "0006_membershiptier_free_admissions_per_month"),
    ]

    operations = [
        migrations.RunPython(set_allowances, clear_allowances),
    ]
```

Note it uses `.filter(...).update(...)` rather than `get()`: a tier that is not there
is not an error worth failing a deploy over, unlike migration 0005's slug lookup where
a miss would have silently dropped data.

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python manage.py test audience -v 2`
Expected: PASS, including the three new tests.

- [ ] **Step 8: Confirm no stray migrations**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: exit 0, "No changes detected".

- [ ] **Step 9: Lint and commit**

Run: `.venv/bin/python -m flake8 audience`
Expected: no output.

```bash
git add audience
git commit -m "feat(audience): per-tier monthly free admission allowance

Cinema Supporter includes one free admission a month, Family Plus four.
The other three tiers include none. Editable in the admin afterwards, so
these are a starting point rather than a truth.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 2: The `FreeAdmission` record

**Files:**
- Create: `audience/models/free_admission.py`
- Modify: `audience/models/__init__.py`
- Modify: `audience/admin.py`
- Create: `audience/migrations/0008_freeadmission.py` (generated)
- Test: `audience/tests/test_free_admission.py`

**Interfaces:**
- Consumes: `Member` (existing).
- Produces: `FreeAdmission(member, redeemed_on, note, recorded_by, created_at)`, reverse accessor `member.free_admissions`, exported from `audience.models`.

- [ ] **Step 1: Write the failing tests**

Create `audience/tests/test_free_admission.py`:

```python
import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from audience.models import FreeAdmission, Member


def make_member(first="Marguerite", last="Ouellette", email="m.o@example.com"):
    return Member.objects.create(
        first_name=first, last_name=last, email=email
    )


class FreeAdmissionTests(TestCase):
    def setUp(self) -> None:
        self.member = make_member()

    def test_redeemed_on_defaults_to_today(self) -> None:
        admission = FreeAdmission.objects.create(member=self.member)
        self.assertEqual(admission.redeemed_on, timezone.localdate())

    def test_reverse_accessor(self) -> None:
        FreeAdmission.objects.create(member=self.member)
        self.assertEqual(self.member.free_admissions.count(), 1)

    def test_ordering_is_newest_first(self) -> None:
        for day in (3, 1, 2):
            FreeAdmission.objects.create(
                member=self.member, redeemed_on=datetime.date(2026, 9, day)
            )
        self.assertEqual(
            [a.redeemed_on.day for a in self.member.free_admissions.all()],
            [3, 2, 1],
        )

    def test_note_is_optional(self) -> None:
        self.assertEqual(FreeAdmission.objects.create(member=self.member).note, "")

    def test_nothing_stops_exceeding_the_allowance(self) -> None:
        """The allowance is a policy the UI warns about, not a constraint."""
        today = timezone.localdate()
        for _ in range(5):
            FreeAdmission.objects.create(member=self.member, redeemed_on=today)
        self.assertEqual(self.member.free_admissions.count(), 5)

    def test_deleting_the_member_deletes_their_redemptions(self) -> None:
        FreeAdmission.objects.create(member=self.member)
        self.member.delete()
        self.assertEqual(FreeAdmission.objects.count(), 0)


class RecordedByTests(TestCase):
    def setUp(self) -> None:
        self.member = make_member()
        self.staff = User.objects.create_user(
            username="bgoding", password="pw12345", is_staff=True
        )

    def test_records_who_gave_it(self) -> None:
        admission = FreeAdmission.objects.create(
            member=self.member, recorded_by=self.staff
        )
        admission.refresh_from_db()
        self.assertEqual(admission.recorded_by, self.staff)

    def test_deleting_the_staff_account_keeps_the_record(self) -> None:
        """Losing an employee must not erase what they did."""
        admission = FreeAdmission.objects.create(
            member=self.member, recorded_by=self.staff
        )
        self.staff.delete()
        admission.refresh_from_db()
        self.assertIsNone(admission.recorded_by)
        self.assertEqual(FreeAdmission.objects.count(), 1)

    def test_recorded_by_is_optional(self) -> None:
        self.assertIsNone(
            FreeAdmission.objects.create(member=self.member).recorded_by
        )
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test audience.tests.test_free_admission -v 2`
Expected: FAIL — `ImportError: cannot import name 'FreeAdmission'`.

- [ ] **Step 3: Write the model**

Create `audience/models/free_admission.py`:

```python
from django.conf import settings
from django.db import models
from django.utils import timezone


class FreeAdmission(models.Model):
    """One free admission, given to one member, on one day.

    Deliberately not linked to a showtime: the counter records that the
    benefit was used, not what was watched. Asking whoever is serving to
    pick a screening from a list would buy that answer with friction on
    every transaction, and a nullable link can be added later without
    disturbing a single existing row.

    There is no constraint stopping a member exceeding their tier's monthly
    allowance. The allowance is a policy the UI warns about and staff may
    override — encoding it as an invariant would make the supported
    workflow impossible.
    """

    member = models.ForeignKey(
        "audience.Member",
        related_name="free_admissions",
        on_delete=models.CASCADE,
    )
    redeemed_on = models.DateField(
        default=timezone.localdate,
        help_text="Which calendar month this counts against.",
    )
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Cleared rather than deleted if the staff account goes away.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-redeemed_on", "-created_at"]
        verbose_name = "Free admission"
        verbose_name_plural = "Free admissions"

    def __str__(self) -> str:
        return f"{self.member.full_name} — {self.redeemed_on}"
```

`default=timezone.localdate` passes the callable, not a value, so each row is stamped
when it is created rather than when the module was imported.

- [ ] **Step 4: Export it**

In `audience/models/__init__.py`, add the import and the `__all__` entry, keeping both
lists in the order the file already uses:

```python
from .free_admission import FreeAdmission
```

and `"FreeAdmission",` in `__all__`.

- [ ] **Step 5: Register it in the admin**

In `audience/admin.py`, add `FreeAdmission` to the `from .models import (...)` block,
then add after `MembershipBenefitAdmin`:

```python
@admin.register(FreeAdmission)
class FreeAdmissionAdmin(admin.ModelAdmin):
    list_display = ("member", "redeemed_on", "recorded_by")
    list_filter = ("redeemed_on",)
    search_fields = ("member__first_name", "member__last_name", "member__email")
    date_hierarchy = "redeemed_on"
    autocomplete_fields = ("member",)
```

`autocomplete_fields` requires the target admin to declare `search_fields`.
`MemberAdmin` already has `search_fields = ("last_name", "first_name", "email")`, so
this works as written — no change to `MemberAdmin` is needed.

- [ ] **Step 6: Generate the migration**

Run: `.venv/bin/python manage.py makemigrations audience -n freeadmission`
Expected: creates `audience/migrations/0008_freeadmission.py` with a single
`CreateModel`.

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python manage.py test audience -v 2`
Expected: PASS, including the nine new tests.

- [ ] **Step 8: Check the admin pages render**

The tier admin shipped a `KeyError` on 2026-09-13 that a method-level test missed, so
admin screens are asserted by asking for the page. Append to
`audience/tests/test_admin.py`:

```python
    def test_free_admission_pages(self) -> None:
        member = Member.objects.create(
            first_name="Denis", last_name="Bouchard", email="d.b@example.com"
        )
        admission = FreeAdmission.objects.create(member=member)
        self.assertRenders("admin:audience_freeadmission_changelist")
        self.assertRenders("admin:audience_freeadmission_add")
        self.assertRenders("admin:audience_freeadmission_change", admission.pk)
```

Add `FreeAdmission` to that module's `from audience.models import (...)` block. The
method belongs on the existing `AudienceAdminSmokeTests` class, which already has the
superuser login and the `assertRenders` helper.

Run: `.venv/bin/python manage.py test audience.tests.test_admin -v 2`
Expected: PASS.

- [ ] **Step 9: Confirm no stray migrations, lint, commit**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: "No changes detected".

Run: `.venv/bin/python -m flake8 audience`
Expected: no output.

```bash
git add audience
git commit -m "feat(audience): record a member's free admissions

One row per redemption: the member, the day, and who recorded it.
recorded_by is SET_NULL so losing an employee does not erase what they
did. Nothing stops a member exceeding their allowance — that is a policy
the UI warns about, and a constraint would make the supported workflow
impossible.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 3: Allowance and usage, derived

The month arithmetic both surfaces depend on. Written and tested before any UI, because
the calendar-month boundary is the thing most likely to be got subtly wrong.

**Files:**
- Modify: `audience/models/member.py`
- Test: `audience/tests/test_free_admission.py` (append)

**Interfaces:**
- Consumes: `Member.current_term` (existing), `FreeAdmission` (Task 2), `MembershipTier.free_admissions_per_month` (Task 1).
- Produces:
  - `Member.free_admission_allowance` → `int` property
  - `Member.free_admissions_in(year: int, month: int)` → `int`
  - `audience.dates.month_bounds(year: int, month: int)` → `tuple[datetime.date, datetime.date]`

- [ ] **Step 1: Write the failing tests**

Append to `audience/tests/test_free_admission.py`:

```python
from decimal import Decimal

from audience.dates import month_bounds
from audience.models import MembershipTerm, MembershipTier


def give_term(member, slug="cinema-supporter", started=None, expires=None):
    tier = MembershipTier.objects.get(slug=slug)
    today = timezone.localdate()
    return MembershipTerm.objects.create(
        member=member,
        tier=tier,
        started_on=started or today - datetime.timedelta(days=30),
        expires_on=expires or today + datetime.timedelta(days=300),
        price_paid=Decimal("120.00"),
    )


class MonthBoundsTests(TestCase):
    def test_a_31_day_month(self) -> None:
        self.assertEqual(
            month_bounds(2026, 8),
            (datetime.date(2026, 8, 1), datetime.date(2026, 8, 31)),
        )

    def test_a_30_day_month(self) -> None:
        self.assertEqual(
            month_bounds(2026, 9),
            (datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)),
        )

    def test_february_in_a_leap_year(self) -> None:
        self.assertEqual(
            month_bounds(2028, 2),
            (datetime.date(2028, 2, 1), datetime.date(2028, 2, 29)),
        )

    def test_february_in_a_common_year(self) -> None:
        self.assertEqual(
            month_bounds(2026, 2),
            (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28)),
        )

    def test_december_does_not_overflow_the_year(self) -> None:
        self.assertEqual(
            month_bounds(2026, 12),
            (datetime.date(2026, 12, 1), datetime.date(2026, 12, 31)),
        )


class AllowanceTests(TestCase):
    def setUp(self) -> None:
        self.member = make_member()

    def test_comes_from_the_current_terms_tier(self) -> None:
        give_term(self.member, "cinema-supporter")
        self.assertEqual(self.member.free_admission_allowance, 1)

    def test_family_plus_gets_four(self) -> None:
        give_term(self.member, "family-plus")
        self.assertEqual(self.member.free_admission_allowance, 4)

    def test_a_tier_that_grants_none(self) -> None:
        give_term(self.member, "individual")
        self.assertEqual(self.member.free_admission_allowance, 0)

    def test_a_member_with_no_term_at_all(self) -> None:
        self.assertEqual(self.member.free_admission_allowance, 0)

    def test_a_lapsed_member_gets_nothing(self) -> None:
        """The benefit came with the membership, and the membership is over."""
        today = timezone.localdate()
        give_term(
            self.member,
            "family-plus",
            started=today - datetime.timedelta(days=400),
            expires=today - datetime.timedelta(days=35),
        )
        self.assertEqual(self.member.free_admission_allowance, 0)


class UsageInMonthTests(TestCase):
    def setUp(self) -> None:
        self.member = make_member()
        give_term(self.member, "family-plus")

    def redeem(self, year, month, day) -> None:
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(year, month, day)
        )

    def test_counts_only_that_month(self) -> None:
        self.redeem(2026, 9, 2)
        self.redeem(2026, 9, 20)
        self.redeem(2026, 8, 15)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 2)

    def test_the_last_day_of_the_previous_month_does_not_count(self) -> None:
        """The boundary most likely to be got wrong."""
        self.redeem(2026, 8, 31)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 0)
        self.assertEqual(self.member.free_admissions_in(2026, 8), 1)

    def test_the_first_day_of_the_month_counts(self) -> None:
        self.redeem(2026, 9, 1)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 1)

    def test_the_last_day_of_the_month_counts(self) -> None:
        self.redeem(2026, 9, 30)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 1)

    def test_a_month_with_none(self) -> None:
        self.assertEqual(self.member.free_admissions_in(2026, 9), 0)

    def test_another_members_redemptions_do_not_count(self) -> None:
        other = make_member("Solange", "Pelletier", "s.p@example.com")
        FreeAdmission.objects.create(
            member=other, redeemed_on=datetime.date(2026, 9, 5)
        )
        self.assertEqual(self.member.free_admissions_in(2026, 9), 0)

    def test_usage_is_not_capped_by_the_allowance(self) -> None:
        for day in range(1, 7):
            self.redeem(2026, 9, day)
        self.assertEqual(self.member.free_admissions_in(2026, 9), 6)
        self.assertEqual(self.member.free_admission_allowance, 4)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test audience.tests.test_free_admission -v 2`
Expected: FAIL — `ImportError` for `month_bounds`, then `AttributeError` for the two
`Member` members.

- [ ] **Step 3: Write `month_bounds`**

Append to `audience/dates.py`:

```python
def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    """The first and last dates of a calendar month, both inclusive.

    Free admissions reset on the 1st, so "this month" is a closed date
    range rather than a comparison against a stored period. Returning both
    ends keeps the SQL annotation and the Python count honest about meaning
    the same thing.
    """
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, 1), datetime.date(year, month, last_day)
```

`calendar` is already imported at the top of that module for `add_months`.

- [ ] **Step 4: Add the two `Member` members**

In `audience/models/member.py`, after `status_label`:

```python
    @property
    def free_admission_allowance(self) -> int:
        """Free admissions a month, from the current term's tier.

        Zero for a lapsed member: the benefit came with the membership.
        Reads through `current_term`, which walks the prefetched terms
        rather than querying, so a roster row costs nothing extra.
        """
        term = self.current_term
        return term.tier.free_admissions_per_month if term else 0

    def free_admissions_in(self, year: int, month: int) -> int:
        """How many redemptions fall in that calendar month.

        The roster counts the same thing with a SQL annotation; the two
        must agree, including at month boundaries.
        """
        first, last = month_bounds(year, month)
        return sum(
            1
            for admission in self.free_admissions.all()
            if first <= admission.redeemed_on <= last
        )
```

Import `month_bounds` at the top of the module: `from audience.dates import month_bounds`.

Note `free_admissions_in` iterates the related manager rather than filtering in SQL,
for the same reason `current_term` does: the detail page prefetches
`free_admissions`, and a `.filter()` would issue a fresh query per call and defeat it.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python manage.py test audience -v 2`
Expected: PASS, including the seventeen new tests.

- [ ] **Step 6: Lint and commit**

Run: `.venv/bin/python -m flake8 audience`
Expected: no output.

```bash
git add audience
git commit -m "feat(audience): derive a member's allowance and monthly usage

month_bounds gives a closed date range for a calendar month, so the SQL
annotation the roster will use and the Python count the detail page uses
can be shown to mean the same thing. Allowance reads through the current
term's tier, so a lapsed member has none.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 4: Redeem from the roster

**Files:**
- Modify: `dashboard/member_views.py`
- Modify: `dashboard/templates/dashboard/_member_list.html`
- Modify: `dashboard/templates/dashboard/members.html`
- Modify: `dashboard/urls.py`
- Modify: `dashboard/static/dashboard/css/members.css`
- Test: `dashboard/tests/test_free_admissions.py`
- Test: `dashboard/tests/test_members.py` (the query-count test)

**Interfaces:**
- Consumes: `Member.free_admission_allowance` (Task 3), `FreeAdmission` (Task 2).
- Produces: URL name `dashboard:free_admission_redeem`; each roster member carries `free_used_this_month` (int).

- [ ] **Step 1: Write the failing tests**

Create `dashboard/tests/test_free_admissions.py`:

```python
import datetime
from decimal import Decimal

from audience.models import FreeAdmission, Member, MembershipTerm, MembershipTier
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone


def make_member(first="Marguerite", last="Ouellette", email="m.o@example.com"):
    return Member.objects.create(first_name=first, last_name=last, email=email)


def give_term(member, slug="cinema-supporter"):
    today = timezone.localdate()
    return MembershipTerm.objects.create(
        member=member,
        tier=MembershipTier.objects.get(slug=slug),
        started_on=today - datetime.timedelta(days=30),
        expires_on=today + datetime.timedelta(days=300),
        price_paid=Decimal("120.00"),
    )


class StaffClient(TestCase):
    def setUp(self) -> None:
        self.staff = User.objects.create_user(
            username="s", password="pw12345", is_staff=True
        )
        self.client.login(username="s", password="pw12345")


class RosterColumnTests(StaffClient):
    def roster(self) -> str:
        return self.client.get(reverse("dashboard:members")).content.decode()

    def test_shows_used_over_allowance(self) -> None:
        give_term(make_member(), "cinema-supporter")
        self.assertIn("0 / 1", self.roster())

    def test_counts_this_months_redemptions(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        FreeAdmission.objects.create(member=member)
        FreeAdmission.objects.create(member=member)
        self.assertIn("2 / 4", self.roster())

    def test_last_months_redemptions_do_not_count(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        first_of_month = timezone.localdate().replace(day=1)
        FreeAdmission.objects.create(
            member=member, redeemed_on=first_of_month - datetime.timedelta(days=1)
        )
        self.assertIn("0 / 4", self.roster())

    def test_a_tier_granting_none_shows_a_dash_and_no_button(self) -> None:
        give_term(make_member(), "individual")
        html = self.roster()
        self.assertNotIn("0 / 0", html)
        self.assertNotIn("Redeem", html)

    def test_a_lapsed_member_shows_no_button(self) -> None:
        make_member()
        self.assertNotIn("Redeem", self.roster())

    def test_over_allowance_is_visible(self) -> None:
        member = make_member()
        give_term(member, "cinema-supporter")
        FreeAdmission.objects.create(member=member)
        FreeAdmission.objects.create(member=member)
        self.assertIn("2 / 1", self.roster())


class BothCountingPathsAgreeTests(StaffClient):
    """The roster counts in SQL; the detail page counts in Python.

    Two implementations of "this calendar month" is two chances to get the
    boundary wrong in different directions, so this pins them against one
    another on the same fixture rather than trusting that each one's own
    boundary test was enough.
    """

    def test_they_report_the_same_number(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        first_of_month = timezone.localdate().replace(day=1)
        FreeAdmission.objects.create(member=member, redeemed_on=first_of_month)
        FreeAdmission.objects.create(member=member, redeemed_on=timezone.localdate())
        FreeAdmission.objects.create(
            member=member, redeemed_on=first_of_month - datetime.timedelta(days=1)
        )

        from dashboard.member_views import member_roster

        request = self.client.get(reverse("dashboard:members")).wsgi_request
        annotated = {m.pk: m.free_used_this_month for m in member_roster(request)[0]}

        today = timezone.localdate()
        self.assertEqual(
            annotated[member.pk],
            member.free_admissions_in(today.year, today.month),
        )
        self.assertEqual(annotated[member.pk], 2)


class RedeemTests(StaffClient):
    def setUp(self) -> None:
        super().setUp()
        self.member = make_member()
        give_term(self.member, "cinema-supporter")
        self.url = reverse(
            "dashboard:free_admission_redeem", args=[self.member.pk]
        )

    def test_records_a_redemption(self) -> None:
        self.client.post(self.url)
        self.assertEqual(self.member.free_admissions.count(), 1)

    def test_dated_today(self) -> None:
        self.client.post(self.url)
        self.assertEqual(
            self.member.free_admissions.first().redeemed_on, timezone.localdate()
        )

    def test_records_who_did_it(self) -> None:
        self.client.post(self.url)
        self.assertEqual(
            self.member.free_admissions.first().recorded_by, self.staff
        )

    def test_swaps_the_list_back(self) -> None:
        html = self.client.post(self.url).content.decode()
        self.assertIn('id="member-list"', html)
        self.assertIn("hx-swap-oob", html)

    def test_toasts(self) -> None:
        resp = self.client.post(self.url)
        self.assertIn("dashboard-toast", resp["HX-Trigger"])

    def test_allows_going_over_the_allowance(self) -> None:
        """Staff judgement wins; the UI warns, the server does not refuse."""
        self.client.post(self.url)
        self.client.post(self.url)
        self.assertEqual(self.member.free_admissions.count(), 2)

    def test_get_is_not_allowed(self) -> None:
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)


class HouseTotalTests(StaffClient):
    def test_counts_every_member_this_month(self) -> None:
        for i in range(3):
            member = make_member(f"F{i}", f"L{i}", f"m{i}@example.com")
            give_term(member, "family-plus")
            FreeAdmission.objects.create(member=member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("3 free admissions given", html)

    def test_ignores_the_roster_filters(self) -> None:
        """A house figure, not a total of the rows on screen."""
        for i in range(3):
            member = make_member(f"F{i}", f"L{i}", f"m{i}@example.com")
            give_term(member, "family-plus")
            FreeAdmission.objects.create(member=member)
        html = self.client.get(
            reverse("dashboard:members"), {"q": "L1"}
        ).content.decode()
        self.assertIn("3 free admissions given", html)

    def test_singular(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        FreeAdmission.objects.create(member=member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("1 free admission given", html)

    def test_last_month_does_not_count(self) -> None:
        member = make_member()
        give_term(member, "family-plus")
        first_of_month = timezone.localdate().replace(day=1)
        FreeAdmission.objects.create(
            member=member, redeemed_on=first_of_month - datetime.timedelta(days=1)
        )
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("0 free admissions given", html)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_free_admissions -v 2`
Expected: FAIL — `NoReverseMatch: 'free_admission_redeem'`.

- [ ] **Step 3: Annotate the roster and add the house total**

In `dashboard/member_views.py`, add to the imports:

```python
from audience.dates import month_bounds
from audience.models import FreeAdmission, Member, MembershipTerm
from django.db.models import Count, Q
```

In `member_roster`, annotate before the queryset is materialised — the existing
`members = list(members)` runs after the status filter, so the annotation must be
applied at the top:

```python
    first, last = month_bounds(*this_month())
    members = Member.objects.prefetch_related("terms__tier").annotate(
        free_used_this_month=Count(
            "free_admissions",
            filter=Q(free_admissions__redeemed_on__range=(first, last)),
        )
    )
```

Exactly one relation is joined here (`free_admissions`); `terms__tier` is
*prefetched*, which issues separate queries rather than joining. That is what keeps the
count correct. If anyone later turns that prefetch into a `select_related` or a second
`annotate` over `terms`, the two joins multiply and every member's free-admission count
silently inflates. Leave the prefetch alone.

and add a module-level helper beside `STATUS_FILTERS`:

```python
def this_month() -> tuple[int, int]:
    today = timezone.localdate()
    return today.year, today.month
```

with `from django.utils import timezone` imported.

In `MemberListView.get`, add the house total to the context — one aggregate over the
whole cinema, deliberately ignoring `?q=` and `?status=`:

```python
        first, last = month_bounds(*this_month())
        free_given_this_month = FreeAdmission.objects.filter(
            redeemed_on__range=(first, last)
        ).count()
```

and pass `"free_given_this_month": free_given_this_month` plus
`"this_month_label": timezone.localdate().strftime("%B")` in the context dict.

- [ ] **Step 4: Write the redeem view**

Append to `dashboard/member_views.py`:

```python
class FreeAdmissionRedeemView(StaffRequiredMixin, View):
    """Record one free admission for a member.

    Deliberately does not check the allowance. The screen warns before
    calling this when the member is already at their limit, and staff may
    go ahead — a two-screen cinema runs on the judgement of whoever is at
    the counter, and a server-side refusal would make the one legitimate
    override impossible.
    """

    def post(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        FreeAdmission.objects.create(member=member, recorded_by=request.user)
        return _member_list_response(
            request, f"Free admission recorded for {member.full_name}"
        )
```

- [ ] **Step 5: Add the column and the button**

In `dashboard/templates/dashboard/_member_list.html`, the header row becomes:

```html
        <tr><th>Name</th><th>Email</th><th>Phone</th><th>Tier</th><th>Free this month</th><th>Expires</th><th>Status</th><th>Actions</th></tr>
```

and a new cell goes after the Tier cell:

```html
          <td>
            {% if member.free_admission_allowance %}
              <span class="freeCount{% if member.free_used_this_month > member.free_admission_allowance %} freeCount--over{% endif %}">{{ member.free_used_this_month }} / {{ member.free_admission_allowance }}</span>
            {% else %}—{% endif %}
          </td>
```

and a Redeem button as the first entry inside the existing `<div class="actions">`,
rendered only when the member has an allowance:

```html
              {% if member.free_admission_allowance %}
              <button class="actionButton" hx-post="{% url 'dashboard:free_admission_redeem' member.pk %}"
                      hx-target="#member-list" hx-swap="outerHTML"
                      {% if member.free_used_this_month >= member.free_admission_allowance %}data-dashboard-confirm='{"title":"Over the monthly allowance","message":"{{ member.full_name|escapejs }} has used {{ member.free_used_this_month }} of {{ member.free_admission_allowance }} free admission(s) this month. Record another?","confirmLabel":"Record anyway","variant":"warning"}'{% endif %}>Redeem</button>
              {% endif %}
```

The confirmation attribute is rendered only at or over the limit, so the common case
stays a single click. It reuses `data-dashboard-confirm`, the same declarative
confirmation the Delete buttons already use.

- [ ] **Step 6: Show the house total**

In `dashboard/templates/dashboard/members.html`, the subtitle line becomes:

```html
      <p class="subtitle">{{ active_count }} active member{{ active_count|pluralize }}. {{ this_month_label }}: {{ free_given_this_month }} free admission{{ free_given_this_month|pluralize }} given.</p>
```

- [ ] **Step 7: Style the count**

Append to `dashboard/static/dashboard/css/members.css`:

```css
/* Free-admission count on the roster. Over-allowance is worth seeing at a
 * glance without being an error — going over is allowed, on purpose. */
.freeCount {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.freeCount--over {
  color: #8a6111;
  font-weight: 600;
}
```

- [ ] **Step 8: Wire the URL**

In `dashboard/urls.py`, after the member entries:

```python
    path(
        "members/<int:pk>/free-admissions/redeem",
        member_views.FreeAdmissionRedeemView.as_view(),
        name="free_admission_redeem",
    ),
```

- [ ] **Step 9: Update the query-count test**

`dashboard/tests/test_members.py`'s `MemberRosterQueryCountTests` pins the roster at 6
queries. The annotation rides along on the existing member query, but the house total
is a new aggregate, so the count becomes **7**.

Update the number and extend the docstring to name the seventh query. Then verify the
test still discriminates: temporarily change the annotation's `filter=` to drop the
date range, confirm the roster tests fail, and restore it. Report that evidence.

Also add a redemption to that test's fixture loop, so the annotated query is exercised
with rows rather than against an empty table:

```python
            if i % 2 == 0:
                FreeAdmission.objects.create(member=member)
```

with `FreeAdmission` imported in that module.

- [ ] **Step 10: Run the tests**

Run: `.venv/bin/python manage.py test dashboard -v 2`
Expected: PASS.

- [ ] **Step 11: Run the whole suite**

Run: `.venv/bin/python manage.py test`
Expected: PASS. Report the exact counts.

- [ ] **Step 12: Lint and commit**

Run: `.venv/bin/python -m flake8 audience dashboard/member_views.py dashboard/tests/test_free_admissions.py dashboard/tests/test_members.py`
Expected: no output.

```bash
git add audience dashboard
git commit -m "feat(dashboard): redeem a free admission from the roster

A Free this month column showing used over allowance, and a one-click
Redeem on rows that have one. At or over the allowance the button asks
first, using the same declarative confirmation the Delete buttons use,
and then records it anyway — the warning is for the person deciding, not
a refusal.

The header carries the house total for the month, which deliberately
ignores the roster filters: filtering to one surname must not make it
look like the cinema gave away one free admission all month.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

### Task 5: The history panel on the member page

**Files:**
- Modify: `dashboard/member_views.py`
- Create: `dashboard/templates/dashboard/_free_admission_list.html`
- Modify: `dashboard/templates/dashboard/member_detail.html`
- Modify: `dashboard/urls.py`
- Modify: `dashboard/static/dashboard/css/members.css`
- Test: `dashboard/tests/test_free_admissions.py` (append)

**Interfaces:**
- Consumes: `Member.free_admissions_in` (Task 3), `dashboard:free_admission_redeem` (Task 4).
- Produces: URL name `dashboard:free_admission_delete`.

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/tests/test_free_admissions.py`:

```python
class DetailPanelTests(StaffClient):
    def setUp(self) -> None:
        super().setUp()
        self.member = make_member()
        give_term(self.member, "family-plus")
        self.url = reverse("dashboard:member_detail", args=[self.member.pk])

    def page(self) -> str:
        return self.client.get(self.url).content.decode()

    def test_groups_by_month_with_a_used_over_allowance_header(self) -> None:
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 9, 14)
        )
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 9, 6)
        )
        html = self.page()
        self.assertIn("September 2026", html)
        self.assertIn("2 of 4 used", html)

    def test_separates_months(self) -> None:
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 9, 2)
        )
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 8, 30)
        )
        html = self.page()
        self.assertIn("September 2026", html)
        self.assertIn("August 2026", html)

    def test_newest_month_first(self) -> None:
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 8, 30)
        )
        FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 9, 2)
        )
        html = self.page()
        self.assertLess(html.index("September 2026"), html.index("August 2026"))

    def test_shows_who_recorded_it(self) -> None:
        FreeAdmission.objects.create(member=self.member, recorded_by=self.staff)
        self.assertIn("s", self.page())

    def test_empty_state(self) -> None:
        self.assertIn("No free admissions yet", self.page())


class DeleteRedemptionTests(StaffClient):
    def setUp(self) -> None:
        super().setUp()
        self.member = make_member()
        give_term(self.member, "family-plus")
        self.admission = FreeAdmission.objects.create(member=self.member)
        self.url = reverse(
            "dashboard:free_admission_delete", args=[self.admission.pk]
        )

    def test_deletes_it(self) -> None:
        self.client.post(self.url)
        self.assertEqual(FreeAdmission.objects.count(), 0)

    def test_leaves_other_redemptions_alone(self) -> None:
        other = FreeAdmission.objects.create(
            member=self.member, redeemed_on=datetime.date(2026, 8, 1)
        )
        self.client.post(self.url)
        self.assertTrue(FreeAdmission.objects.filter(pk=other.pk).exists())

    def test_swaps_the_panel_back(self) -> None:
        html = self.client.post(self.url).content.decode()
        self.assertIn('id="free-admission-list"', html)
        self.assertIn("hx-swap-oob", html)

    def test_toasts(self) -> None:
        self.assertIn("dashboard-toast", self.client.post(self.url)["HX-Trigger"])

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.post(self.url).status_code, 302)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_free_admissions -v 2`
Expected: FAIL — `NoReverseMatch: 'free_admission_delete'`, and the panel assertions
fail because the detail page has no panel yet.

- [ ] **Step 3: Group the redemptions by month**

Append to `dashboard/member_views.py`:

```python
def _free_admission_months(member):
    """This member's redemptions, newest month first.

    Grouped in Python over the prefetched rows rather than with a database
    aggregate: a member has a handful of these a year, and grouping here
    lets each month reuse `free_admissions_in` so the header count and the
    rows below it cannot disagree.
    """
    months = []
    for admission in member.free_admissions.all():
        key = (admission.redeemed_on.year, admission.redeemed_on.month)
        if not months or months[-1]["key"] != key:
            months.append(
                {
                    "key": key,
                    "label": admission.redeemed_on.strftime("%B %Y"),
                    "used": member.free_admissions_in(*key),
                    "admissions": [],
                }
            )
        months[-1]["admissions"].append(admission)
    return months
```

This relies on `FreeAdmission.Meta.ordering` being newest-first, so rows for one month
arrive together.

Then a response helper mirroring `_term_list_response`:

```python
def _free_admission_list_response(request, member, toast_message):
    """Success response: OOB-swap the panel and toast."""
    member = Member.objects.prefetch_related("terms__tier", "free_admissions").get(
        pk=member.pk
    )
    html = render(
        request,
        "dashboard/_free_admission_list.html",
        {"member": member, "free_admission_months": _free_admission_months(member)},
    ).content.decode()
    html = html.replace(
        '<div id="free-admission-list">',
        '<div id="free-admission-list" hx-swap-oob="true">',
        1,
    )
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps(
        {"dashboard-toast": {"kind": "success", "message": toast_message}}
    )
    return resp


class FreeAdmissionDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        admission = get_object_or_404(FreeAdmission, pk=pk)
        member = admission.member
        admission.delete()
        return _free_admission_list_response(
            request, member, "Free admission removed"
        )
```

In `MemberDetailView.get`, prefetch the redemptions and pass the grouping:

```python
        member = get_object_or_404(
            Member.objects.prefetch_related("terms__tier", "free_admissions"),
            pk=pk,
        )
        return render(
            request,
            "dashboard/member_detail.html",
            {
                "member": member,
                "terms": member.terms.all(),
                "free_admission_months": _free_admission_months(member),
            },
        )
```

- [ ] **Step 4: Write the panel template**

Create `dashboard/templates/dashboard/_free_admission_list.html`:

```html
<div id="free-admission-list">
  <h2 class="panelTitle">Free admissions</h2>
  {% if free_admission_months %}
  <div class="tableWrapper">
    <table class="table">
      <tbody>
        {% for month in free_admission_months %}
        <tr class="monthRow">
          <th colspan="3">{{ month.label }} — {{ month.used }} of {{ member.free_admission_allowance }} used</th>
        </tr>
        {% for admission in month.admissions %}
        <tr>
          <td>{{ admission.redeemed_on|date:"M j, Y" }}</td>
          <td>{{ admission.recorded_by|default:"—" }}</td>
          <td>
            <div class="actions">
              <button class="actionButton deleteButton"
                      hx-post="{% url 'dashboard:free_admission_delete' admission.pk %}"
                      hx-target="#free-admission-list" hx-swap="outerHTML"
                      data-dashboard-confirm='{"title":"Remove Free Admission","message":"Remove the free admission dated {{ admission.redeemed_on|date:"M j, Y" }}? This cannot be undone.","confirmLabel":"Remove","variant":"danger"}'>Remove</button>
            </div>
          </td>
        </tr>
        {% endfor %}
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="empty-state">
    <h3 class="empty-state-title">No free admissions yet</h3>
    <p class="empty-state-description">Redeem one from the roster when this member uses a free admission.</p>
  </div>
  {% endif %}
</div>
```

- [ ] **Step 5: Put the panel on the page**

In `dashboard/templates/dashboard/member_detail.html`, after the term list include:

```html
  {% include "dashboard/_free_admission_list.html" %}
```

- [ ] **Step 6: Style the panel**

Append to `dashboard/static/dashboard/css/members.css`:

```css
.panelTitle {
  font-family: 'Playfair Display', serif;
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--charcoal);
  margin: 2rem 0 0.75rem;
}

/* Month headers inside the free-admission table. */
.monthRow th {
  text-align: left;
  background: var(--cream);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--stone);
  padding: 0.6rem 1rem;
}
```

- [ ] **Step 7: Wire the URL**

In `dashboard/urls.py`, after the redeem entry:

```python
    path(
        "free-admissions/<int:pk>/delete",
        member_views.FreeAdmissionDeleteView.as_view(),
        name="free_admission_delete",
    ),
```

- [ ] **Step 8: Run the tests**

Run: `.venv/bin/python manage.py test dashboard -v 2`
Expected: PASS.

- [ ] **Step 9: Run the whole suite**

Run: `.venv/bin/python manage.py test`
Expected: PASS, no failures and no errors. Report the exact counts.

- [ ] **Step 10: Confirm no stray migrations**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: exit 0, "No changes detected".

- [ ] **Step 11: Lint everything this plan touched**

Run: `.venv/bin/python -m flake8 audience dashboard/member_views.py dashboard/tests/test_free_admissions.py dashboard/tests/test_members.py`
Expected: no output. Pre-existing violations elsewhere in `dashboard/` are not this
plan's to fix.

- [ ] **Step 12: Commit**

```bash
git add dashboard
git commit -m "feat(dashboard): free admission history on the member page

Grouped by calendar month, newest first, each month headed with how many
of the allowance were used. Each row can be removed, because staff will
mis-click and the fix should not need the Django admin.

The month header reuses free_admissions_in, so the count and the rows
beneath it cannot disagree.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KsWB1YFrTFKDQUvkL7Qp9g"
```

---

## Deployment

`manage.py migrate` and nothing else. No environment variables, no external
configuration, no public-site change — everything here is behind staff login.

The two allowance numbers ship in migration 0007 and are editable in the admin
afterwards, so getting one wrong is a correction rather than a release.

The local database is stale sqlite, not production. Nothing here can be verified
against real membership data before deploy.
