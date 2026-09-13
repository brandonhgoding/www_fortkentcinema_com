# Membership Records Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the membership spreadsheet with a staff-only roster in the dashboard — members, their renewal history, and a CSV export.

**Architecture:** Two new models in the existing `audience` app (`Member`, `MembershipTerm`), where a renewal appends a term rather than mutating dates, and membership status is derived from today's date instead of stored. The staff UI is a new `dashboard/member_views.py` following the Screens CRUD pattern exactly — drawer form, htmx out-of-band list swap, `HX-Trigger` toast.

**Tech Stack:** Django 5.2.3, htmx + Alpine (already wired into `base_dashboard.html`), Django templates, `manage.py test` + `flake8`.

**Spec:** `docs/superpowers/specs/2026-09-11-membership-records-design.md`

## Global Constraints

- **Python is `.venv/bin/python`.** There is no bare `python` on this machine. Every command in this plan runs from the repo root.
- **Tests:** `.venv/bin/python manage.py test <label> -v 2`. Full suite: `.venv/bin/python manage.py test`.
- **Lint:** `.venv/bin/python -m flake8 <paths>` — `max-line-length = 88`, migrations excluded. mypy is configured but cannot run in this checkout; do not attempt it. black is configured but unapplied; do not reformat files you did not write.
- **`audience` must never import `web`.** `web/views.py:15` imports `audience.models`, so the reverse is circular. Tier data reaches the models only through the form layer in `dashboard/`.
- **Expiry is inclusive.** A membership is valid *through* `expires_on`.
- **Expiring-soon window is 30 days.**
- **Every view in this plan is staff-only** via `StaffRequiredMixin` from `dashboard/mixins.py`. The CSV export included.
- **Commits** end with the two attribution lines shown in each commit step. Copy them verbatim.
- **Branch:** all work lands on `feat/membership-records`.

---

### Task 1: Turn `audience/models.py` into a package

Splitting first means every later task adds a file instead of growing one. Same app label and same table names, so this produces **no migration** — if `makemigrations` wants to write one, something has been renamed by accident.

**Files:**
- Create: `audience/models/__init__.py`
- Create: `audience/models/subscriber.py` (content moved verbatim from `audience/models.py`)
- Delete: `audience/models.py`
- Test: `audience/tests/test_models.py` (existing, unchanged — it is the regression test)

**Interfaces:**
- Consumes: nothing
- Produces: `from audience.models import Subscriber, SubscriberStatus` keeps working — every later task and the existing `web/views.py:15` depend on it

- [x] **Step 1: Confirm the current tests pass before touching anything**

Run: `.venv/bin/python manage.py test audience -v 2`
Expected: PASS, 5 tests.

- [x] **Step 2: Move the file**

```bash
mkdir -p audience/models
git mv audience/models.py audience/models/subscriber.py
```

- [x] **Step 3: Write the package `__init__.py`**

Create `audience/models/__init__.py`:

```python
from .subscriber import Subscriber, SubscriberManager, SubscriberStatus

__all__ = [
    "Subscriber",
    "SubscriberManager",
    "SubscriberStatus",
]
```

- [x] **Step 4: Verify nothing moved in the database**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run audience`
Expected: exit 0, "No changes detected". If Django proposes a migration here, stop — the model's `Meta` or app label changed and must be put back.

- [x] **Step 5: Run the tests that prove the imports still resolve**

Run: `.venv/bin/python manage.py test audience dashboard.tests.test_subscribers web.tests.test_vote_subscribe -v 2`
Expected: PASS.

- [x] **Step 6: Lint**

Run: `.venv/bin/python -m flake8 audience`
Expected: no output.

- [x] **Step 7: Commit**

```bash
git add audience/models audience/models.py
git commit -m "refactor(audience): split models.py into a models package

No migration: same app label, same table. Makes room for the
membership models without growing a single file.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01J5vdXGkpYi5e5hYvdUDtAW"
```

---

### Task 2: `add_months` date helper

Both the term's expiry default and the form need "twelve months from this date". Written by hand rather than pulled from `dateutil` — that package is in `requirements.txt` only as a transitive dependency of the optional boto3 stack, and this is six lines.

**Files:**
- Create: `audience/dates.py`
- Test: `audience/tests/test_dates.py`

**Interfaces:**
- Consumes: nothing
- Produces: `add_months(start: datetime.date, months: int) -> datetime.date` — used by Task 3's model default and Task 5's form

- [x] **Step 1: Write the failing test**

Create `audience/tests/test_dates.py`:

```python
import datetime

from django.test import SimpleTestCase

from audience.dates import add_months


class AddMonthsTests(SimpleTestCase):
    def test_adds_a_year(self) -> None:
        self.assertEqual(
            add_months(datetime.date(2026, 9, 11), 12),
            datetime.date(2027, 9, 11),
        )

    def test_crosses_the_year_boundary(self) -> None:
        self.assertEqual(
            add_months(datetime.date(2026, 11, 30), 3),
            datetime.date(2027, 2, 28),
        )

    def test_clamps_to_the_last_day_of_a_shorter_month(self) -> None:
        # There is no 31st of February; a membership sold on the 31st still
        # has to land on a real date.
        self.assertEqual(
            add_months(datetime.date(2026, 1, 31), 1),
            datetime.date(2026, 2, 28),
        )

    def test_lands_on_a_leap_day(self) -> None:
        self.assertEqual(
            add_months(datetime.date(2028, 1, 31), 1),
            datetime.date(2028, 2, 29),
        )

    def test_zero_months_is_the_same_date(self) -> None:
        self.assertEqual(
            add_months(datetime.date(2026, 9, 11), 0),
            datetime.date(2026, 9, 11),
        )
```

- [x] **Step 2: Run it and watch it fail**

Run: `.venv/bin/python manage.py test audience.tests.test_dates -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'audience.dates'`.

- [x] **Step 3: Write the implementation**

Create `audience/dates.py`:

```python
"""Calendar arithmetic for membership terms.

Hand-rolled rather than pulled from dateutil: that package is only present
as a transitive dependency of the optional boto3 stack, and this is the one
calculation we need.
"""

import calendar
import datetime


def add_months(start: datetime.date, months: int) -> datetime.date:
    """Return `start` advanced by `months`, clamped to the target month's length."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)
```

- [x] **Step 4: Run the tests**

Run: `.venv/bin/python manage.py test audience.tests.test_dates -v 2`
Expected: PASS, 5 tests.

- [x] **Step 5: Lint and commit**

```bash
.venv/bin/python -m flake8 audience
git add audience/dates.py audience/tests/test_dates.py
git commit -m "feat(audience): add_months helper for membership terms

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01J5vdXGkpYi5e5hYvdUDtAW"
```

---

### Task 3: `Member` and `MembershipTerm` models

Both models in one migration, because a member without terms is not a thing the application ever wants. Derived status arrives in Task 4 — this task is fields, normalization, ordering, and cascade.

**Files:**
- Create: `audience/models/member.py`
- Create: `audience/models/membership_term.py`
- Modify: `audience/models/__init__.py`
- Modify: `audience/admin.py`
- Create: `audience/migrations/0002_member_membershipterm.py` (generated)
- Test: `audience/tests/test_member.py`

**Interfaces:**
- Consumes: `add_months` from Task 2
- Produces:
  - `Member(first_name, last_name, email, phone, notes, created_at, updated_at)`, `Meta.ordering = ["last_name", "first_name"]`, `full_name` property
  - `MembershipTerm(member, tier, started_on, expires_on, price_paid, purchased_at, notes, created_at)`, `related_name="terms"`, `Meta.ordering = ["-started_on"]`, `default_expiry(started_on, duration_months)` staticmethod
  - Tasks 4-9 rely on all of these names

- [x] **Step 1: Write the failing tests**

Create `audience/tests/test_member.py`:

```python
import datetime
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from audience.models import Member, MembershipTerm


class MemberFieldTests(TestCase):
    def test_email_is_lowercased_on_save(self) -> None:
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="  Ada@Example.COM "
        )
        member.refresh_from_db()
        self.assertEqual(member.email, "ada@example.com")

    def test_email_is_unique(self) -> None:
        Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        with self.assertRaises(IntegrityError):
            Member.objects.create(
                first_name="Another", last_name="Ada", email="ada@example.com"
            )

    def test_full_name(self) -> None:
        member = Member(first_name="Ada", last_name="Lovelace")
        self.assertEqual(member.full_name, "Ada Lovelace")

    def test_ordering_is_by_surname(self) -> None:
        Member.objects.create(
            first_name="Zoe", last_name="Adams", email="z@example.com"
        )
        Member.objects.create(
            first_name="Amy", last_name="Baker", email="a@example.com"
        )
        self.assertEqual(
            [m.last_name for m in Member.objects.all()], ["Adams", "Baker"]
        )

    def test_phone_and_notes_are_optional(self) -> None:
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.assertEqual(member.phone, "")
        self.assertEqual(member.notes, "")


class MembershipTermTests(TestCase):
    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )

    def _term(self, **kwargs) -> MembershipTerm:
        defaults = {
            "member": self.member,
            "tier": "individual",
            "started_on": datetime.date(2026, 1, 1),
            "expires_on": datetime.date(2027, 1, 1),
            "price_paid": Decimal("60.00"),
        }
        return MembershipTerm.objects.create(**{**defaults, **kwargs})

    def test_terms_are_reachable_from_the_member(self) -> None:
        term = self._term()
        self.assertEqual(list(self.member.terms.all()), [term])

    def test_terms_are_newest_first(self) -> None:
        older = self._term(started_on=datetime.date(2025, 1, 1))
        newer = self._term(started_on=datetime.date(2026, 1, 1))
        self.assertEqual(list(self.member.terms.all()), [newer, older])

    def test_deleting_a_member_deletes_their_terms(self) -> None:
        self._term()
        self.member.delete()
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_default_expiry_is_start_plus_the_tier_duration(self) -> None:
        self.assertEqual(
            MembershipTerm.default_expiry(datetime.date(2026, 9, 11), 12),
            datetime.date(2027, 9, 11),
        )
```

- [x] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test audience.tests.test_member -v 2`
Expected: FAIL — `ImportError: cannot import name 'Member' from 'audience.models'`.

- [x] **Step 3: Write `Member`**

Create `audience/models/member.py`:

```python
from typing import ClassVar

from django.db import models


class MemberManager(models.Manager):
    pass


class Member(models.Model):
    """A cardholder.

    Family tiers cover the cardholder plus immediate family, but only the
    cardholder is stored — coverage stays honour-system at the box office,
    exactly as it works today.
    """

    objects: ClassVar[MemberManager] = MemberManager()

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)

    # Free text on purpose: people give us "543-7000" and "+1 207 555 0100"
    # alike, and validating a local roster's phone numbers buys nothing.
    phone = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "Member"
        verbose_name_plural = "Members"

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def save(self, *args, **kwargs) -> None:
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)
```

- [x] **Step 4: Write `MembershipTerm`**

Create `audience/models/membership_term.py`:

```python
import datetime

from django.db import models

from audience.dates import add_months


class MembershipTerm(models.Model):
    """One purchased membership period.

    A renewal appends a term rather than moving dates on the member, so
    renewals, tier changes and lapses stay visible instead of being
    overwritten. Overlapping terms are allowed: a double-entered renewal is
    a data-entry mistake to notice in the UI, not an integrity violation
    worth a constraint that would also block a legitimate early renewal.
    """

    member = models.ForeignKey(
        "audience.Member", related_name="terms", on_delete=models.CASCADE
    )

    # The tier slug from web.constants.MEMBERSHIP. Stored as a plain string
    # because `web` imports `audience` — validating against the catalogue
    # happens in dashboard.forms, where importing `web` is safe.
    tier = models.CharField(max_length=32)

    started_on = models.DateField()
    expires_on = models.DateField(help_text="Inclusive: the membership is good through this date.")
    price_paid = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        help_text="What actually changed hands, so a comped or discounted "
        "membership stays truthful and past revenue survives a price change.",
    )
    purchased_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_on"]
        verbose_name = "Membership term"
        verbose_name_plural = "Membership terms"

    def __str__(self) -> str:
        return f"{self.tier}: {self.started_on} – {self.expires_on}"

    @staticmethod
    def default_expiry(
        started_on: datetime.date, duration_months: int
    ) -> datetime.date:
        return add_months(started_on, duration_months)
```

- [x] **Step 5: Export both models**

Replace `audience/models/__init__.py` with:

```python
from .member import Member, MemberManager
from .membership_term import MembershipTerm
from .subscriber import Subscriber, SubscriberManager, SubscriberStatus

__all__ = [
    "Member",
    "MemberManager",
    "MembershipTerm",
    "Subscriber",
    "SubscriberManager",
    "SubscriberStatus",
]
```

- [x] **Step 6: Register them in the Django admin**

`audience/admin.py` already registers `Subscriber`. Append:

```python
from .models import Member, MembershipTerm


class MembershipTermInline(admin.TabularInline):
    model = MembershipTerm
    extra = 0


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "email", "phone")
    search_fields = ("last_name", "first_name", "email")
    inlines = [MembershipTermInline]
```

Fold the new names into the existing `from .models import Subscriber` line rather than adding a second import.

- [x] **Step 7: Generate the migration**

Run: `.venv/bin/python manage.py makemigrations audience`
Expected: creates `audience/migrations/0002_member_membershipterm.py` with two `CreateModel` operations and nothing else. Read it and confirm there is no operation touching `subscriber`.

- [x] **Step 8: Run the tests**

Run: `.venv/bin/python manage.py test audience -v 2`
Expected: PASS — the 5 subscriber tests, 5 date tests, and 9 new member tests.

- [x] **Step 9: Lint and commit**

```bash
.venv/bin/python -m flake8 audience
git add audience
git commit -m "feat(audience): Member and MembershipTerm models

A renewal appends a term rather than mutating the member, so renewal
history survives. Only the cardholder is stored; family coverage stays
honour-system as it is at the counter.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01J5vdXGkpYi5e5hYvdUDtAW"
```

---

### Task 4: Derived status — `current_term`, `is_active`, `status`, and the manager

No stored flag. A stored `is_active` goes stale at midnight on every expiry and needs a scheduled job to stay honest; deriving it means the roster is right every time it loads.

`current_term` iterates `self.terms.all()` rather than issuing a filtered query, so the list view's `prefetch_related("terms")` serves every row from one query. Terms are ordered newest-first, so the newest covering term wins.

**Files:**
- Modify: `audience/models/member.py`
- Modify: `audience/models/membership_term.py`
- Test: `audience/tests/test_member.py` (append)

**Interfaces:**
- Consumes: `Member`, `MembershipTerm` from Task 3
- Produces:
  - `Member.current_term` → `MembershipTerm | None`
  - `Member.is_active` → `bool`
  - `Member.status` → `"active" | "expiring" | "lapsed"`
  - `Member.STATUS_LABELS` → `dict[str, str]`
  - `Member.objects.active(on=None)` / `.lapsed(on=None)` → `QuerySet[Member]`
  - `MembershipTerm.is_current` → `bool`
  - `audience.models.member.EXPIRING_SOON_DAYS = 30`
  - Tasks 6-9 render `status` and filter through `active()` / `lapsed()`

- [x] **Step 1: Write the failing tests**

Append to `audience/tests/test_member.py`:

```python
from django.utils import timezone


class DerivedStatusTests(TestCase):
    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.today = timezone.localdate()

    def _term(self, start_offset: int, end_offset: int) -> MembershipTerm:
        return MembershipTerm.objects.create(
            member=self.member,
            tier="individual",
            started_on=self.today + datetime.timedelta(days=start_offset),
            expires_on=self.today + datetime.timedelta(days=end_offset),
            price_paid=Decimal("60.00"),
        )

    def test_no_terms_means_lapsed(self) -> None:
        self.assertIsNone(self.member.current_term)
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.status, "lapsed")

    def test_active_on_the_first_day(self) -> None:
        self._term(0, 365)
        self.assertTrue(self.member.is_active)

    def test_active_on_the_expiry_date_itself(self) -> None:
        # Inclusive: the membership is good THROUGH expires_on.
        self._term(-365, 0)
        self.assertTrue(self.member.is_active)

    def test_lapsed_the_day_after_expiry(self) -> None:
        self._term(-366, -1)
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.status, "lapsed")

    def test_expiring_soon_within_thirty_days(self) -> None:
        self._term(-335, 29)
        self.assertEqual(self.member.status, "expiring")

    def test_not_expiring_soon_at_thirty_one_days(self) -> None:
        self._term(-334, 31)
        self.assertEqual(self.member.status, "active")

    def test_a_renewal_makes_a_lapsed_member_active_again(self) -> None:
        old = self._term(-800, -400)
        new = self._term(-10, 355)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)
        self.assertEqual(self.member.current_term, new)
        self.assertNotEqual(self.member.current_term, old)

    def test_term_knows_whether_it_is_current(self) -> None:
        self.assertTrue(self._term(-1, 1).is_current)
        self.assertFalse(self._term(-10, -5).is_current)


class MemberManagerTests(TestCase):
    def setUp(self) -> None:
        self.today = timezone.localdate()
        self.active = Member.objects.create(
            first_name="Cur", last_name="Rent", email="current@example.com"
        )
        MembershipTerm.objects.create(
            member=self.active,
            tier="individual",
            started_on=self.today - datetime.timedelta(days=10),
            expires_on=self.today + datetime.timedelta(days=10),
            price_paid=Decimal("60.00"),
        )
        self.lapsed = Member.objects.create(
            first_name="Ex", last_name="Pired", email="lapsed@example.com"
        )
        MembershipTerm.objects.create(
            member=self.lapsed,
            tier="individual",
            started_on=self.today - datetime.timedelta(days=400),
            expires_on=self.today - datetime.timedelta(days=35),
            price_paid=Decimal("60.00"),
        )
        self.never = Member.objects.create(
            first_name="No", last_name="Terms", email="never@example.com"
        )

    def test_active_returns_only_covered_members(self) -> None:
        self.assertEqual(list(Member.objects.active()), [self.active])

    def test_lapsed_includes_members_with_no_terms(self) -> None:
        self.assertEqual(
            sorted(m.email for m in Member.objects.lapsed()),
            ["lapsed@example.com", "never@example.com"],
        )

    def test_active_and_lapsed_partition_the_roster(self) -> None:
        self.assertEqual(
            Member.objects.active().count() + Member.objects.lapsed().count(),
            Member.objects.count(),
        )

    def test_a_member_with_two_terms_is_not_listed_twice(self) -> None:
        MembershipTerm.objects.create(
            member=self.active,
            tier="individual",
            started_on=self.today - datetime.timedelta(days=5),
            expires_on=self.today + datetime.timedelta(days=20),
            price_paid=Decimal("60.00"),
        )
        self.assertEqual(Member.objects.active().count(), 1)
```

- [x] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test audience.tests.test_member -v 2`
Expected: FAIL — `AttributeError: 'Member' object has no attribute 'current_term'`.

- [x] **Step 3: Add `is_current` to the term**

In `audience/models/membership_term.py`, add `from django.utils import timezone` to the imports and this property to `MembershipTerm`:

```python
    @property
    def is_current(self) -> bool:
        return self.started_on <= timezone.localdate() <= self.expires_on
```

- [x] **Step 4: Add the derived attributes and manager methods**

In `audience/models/member.py`, add the imports and replace the stub `MemberManager`:

```python
import datetime
from typing import ClassVar

from django.db import models
from django.utils import timezone

# How close to expiry a membership starts showing an amber pill. Affects the
# colour of a badge and nothing else — no mail is sent.
EXPIRING_SOON_DAYS = 30


class MemberManager(models.Manager):
    def active(self, on: datetime.date | None = None) -> models.QuerySet["Member"]:
        """Members whose terms cover `on` (today by default)."""
        on = on or timezone.localdate()
        return self.filter(
            terms__started_on__lte=on, terms__expires_on__gte=on
        ).distinct()

    def lapsed(self, on: datetime.date | None = None) -> models.QuerySet["Member"]:
        """Everyone else, including members who never had a term."""
        on = on or timezone.localdate()
        return self.exclude(pk__in=self.active(on).values("pk"))
```

And add to `Member`:

```python
    @property
    def current_term(self):
        """The term covering today, or None.

        Iterates the related manager rather than filtering in SQL so that a
        list view's prefetch_related("terms") answers every row from one
        query. Terms are ordered newest-first, so a renewal wins over the
        term it overlaps.
        """
        today = timezone.localdate()
        for term in self.terms.all():
            if term.started_on <= today <= term.expires_on:
                return term
        return None

    @property
    def is_active(self) -> bool:
        return self.current_term is not None

    @property
    def status(self) -> str:
        """One of "active", "expiring", "lapsed" — drives the roster pill."""
        term = self.current_term
        if term is None:
            return "lapsed"
        days_left = (term.expires_on - timezone.localdate()).days
        if days_left <= EXPIRING_SOON_DAYS:
            return "expiring"
        return "active"

    STATUS_LABELS: ClassVar[dict[str, str]] = {
        "active": "Active",
        "expiring": "Expiring soon",
        "lapsed": "Lapsed",
    }

    @property
    def status_label(self) -> str:
        return self.STATUS_LABELS[self.status]
```

- [x] **Step 5: Run the tests**

Run: `.venv/bin/python manage.py test audience -v 2`
Expected: PASS — 31 tests.

- [x] **Step 6: Lint and commit**

```bash
.venv/bin/python -m flake8 audience
git add audience
git commit -m "feat(audience): derive membership status from today's date

No stored is_active flag: it would go stale at midnight on every expiry
and need a cron job to stay honest. Expiry is inclusive.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01J5vdXGkpYi5e5hYvdUDtAW"
```

---

### Task 5: Tier lookups and the two forms

This is the seam where the tier catalogue meets the models. `dashboard` importing `web.constants` is already established — `dashboard/inquiry_views.py:9` does exactly this with `SPONSORSHIP_TIER_LABELS`.

**Files:**
- Modify: `web/constants.py` (after the `MEMBERSHIP` list, before `MEMBERSHIP_FAQ`)
- Modify: `dashboard/forms.py` (append)
- Test: `dashboard/tests/test_member_forms.py`

**Interfaces:**
- Consumes: `Member`, `MembershipTerm` (Task 3); `add_months` (Task 2)
- Produces:
  - `web.constants.MEMBERSHIP_BY_SLUG: dict[str, dict]`
  - `web.constants.MEMBERSHIP_TIER_LABELS: dict[str, str]`
  - `dashboard.forms.MEMBERSHIP_TIER_CHOICES: list[tuple[str, str]]`
  - `dashboard.forms.MemberForm` (fields: `first_name`, `last_name`, `email`, `phone`, `notes`)
  - `dashboard.forms.MembershipTermForm` (fields: `tier`, `started_on`, `expires_on`, `price_paid`, `purchased_at`, `notes`)
  - Tasks 7 and 8 instantiate both

- [x] **Step 1: Write the failing tests**

Create `dashboard/tests/test_member_forms.py`:

```python
import datetime
from decimal import Decimal

from django.test import TestCase

from audience.models import Member
from dashboard.forms import MemberForm, MembershipTermForm


class MemberFormTests(TestCase):
    def test_valid_with_name_and_email_only(self) -> None:
        form = MemberForm(
            {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"}
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_email_is_required(self) -> None:
        form = MemberForm({"first_name": "Ada", "last_name": "Lovelace"})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_duplicate_email_is_rejected_with_a_readable_message(self) -> None:
        Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        form = MemberForm(
            {"first_name": "Other", "last_name": "Person", "email": "ADA@example.com"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class MembershipTermFormTests(TestCase):
    def setUp(self) -> None:
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )

    def test_unknown_tier_is_rejected(self) -> None:
        form = MembershipTermForm(
            {"tier": "platinum-invented", "started_on": "2026-09-11"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("tier", form.errors)

    def test_expiry_defaults_to_the_tier_duration(self) -> None:
        form = MembershipTermForm({"tier": "individual", "started_on": "2026-09-11"})
        self.assertTrue(form.is_valid(), form.errors)
        term = form.save(commit=False)
        term.member = self.member
        term.save()
        self.assertEqual(term.expires_on, datetime.date(2027, 9, 11))

    def test_price_defaults_to_the_tier_price(self) -> None:
        form = MembershipTermForm({"tier": "individual", "started_on": "2026-09-11"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price_paid"], Decimal("60"))

    def test_an_explicit_price_survives(self) -> None:
        form = MembershipTermForm(
            {"tier": "individual", "started_on": "2026-09-11", "price_paid": "0"}
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price_paid"], Decimal("0"))

    def test_an_explicit_expiry_survives(self) -> None:
        form = MembershipTermForm(
            {
                "tier": "individual",
                "started_on": "2026-09-11",
                "expires_on": "2027-03-11",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["expires_on"], datetime.date(2027, 3, 11))

    def test_start_date_is_required(self) -> None:
        form = MembershipTermForm({"tier": "individual"})
        self.assertFalse(form.is_valid())
        self.assertIn("started_on", form.errors)

    def test_every_catalogue_tier_is_offered(self) -> None:
        from web.constants import MEMBERSHIP

        offered = {slug for slug, _label in MembershipTermForm().fields["tier"].choices}
        self.assertEqual(offered, {t["slug"] for t in MEMBERSHIP})
```

- [x] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_member_forms -v 2`
Expected: FAIL — `ImportError: cannot import name 'MemberForm' from 'dashboard.forms'`.

- [x] **Step 3: Add the tier lookups**

In `web/constants.py`, immediately after the closing `]` of the `MEMBERSHIP` list:

```python
MEMBERSHIP_BY_SLUG = {t["slug"]: t for t in MEMBERSHIP}
MEMBERSHIP_TIER_LABELS = {t["slug"]: t["name"] for t in MEMBERSHIP}
```

- [x] **Step 4: Write the forms**

Append to `dashboard/forms.py` (and add `from audience.models import Member, MembershipTerm`, `from audience.dates import add_months`, and `from web.constants import MEMBERSHIP, MEMBERSHIP_BY_SLUG` to the imports at the top):

```python
# The tier catalogue lives in web.constants; `audience` cannot import it
# (web imports audience), so validation against it happens here.
MEMBERSHIP_TIER_CHOICES = [(t["slug"], t["name"]) for t in MEMBERSHIP]


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["first_name", "last_name", "email", "phone", "notes"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
            "phone": forms.TextInput(
                attrs={"class": "input", "placeholder": "optional"}
            ),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 3}),
        }

    def clean_email(self) -> str:
        # Member.save() lowercases; normalise here too so the uniqueness
        # check catches "ADA@" against a stored "ada@".
        return (self.cleaned_data["email"] or "").strip().lower()


class MembershipTermForm(forms.ModelForm):
    tier = forms.ChoiceField(
        choices=MEMBERSHIP_TIER_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
    )

    class Meta:
        model = MembershipTerm
        fields = [
            "tier", "started_on", "expires_on",
            "price_paid", "purchased_at", "notes",
        ]
        widgets = {
            "started_on": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "expires_on": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "purchased_at": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "price_paid": forms.NumberInput(
                attrs={"class": "input", "step": "0.01", "min": "0"}
            ),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 2}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Both are filled from the tier when left blank, so staff can add a
        # renewal by choosing a tier and a start date and nothing else.
        self.fields["expires_on"].required = False
        self.fields["price_paid"].required = False

    def clean(self):
        cleaned = super().clean()
        tier = MEMBERSHIP_BY_SLUG.get(cleaned.get("tier"))
        started_on = cleaned.get("started_on")
        if tier is None:
            return cleaned

        if started_on and not cleaned.get("expires_on"):
            cleaned["expires_on"] = add_months(started_on, tier["duration_months"])
        if cleaned.get("price_paid") is None:
            cleaned["price_paid"] = tier["price"]

        expires_on = cleaned.get("expires_on")
        if started_on and expires_on and expires_on < started_on:
            self.add_error("expires_on", "Expiry cannot be before the start date.")
        return cleaned
```

- [x] **Step 5: Run the tests**

Run: `.venv/bin/python manage.py test dashboard.tests.test_member_forms audience -v 2`
Expected: PASS.

- [x] **Step 6: Confirm the public membership page still renders**

The new dict comprehensions run at import time in `web/constants.py`; a typo there breaks `/membership/`.

Run: `.venv/bin/python manage.py test web.tests.test_pages web.tests.test_analytics -v 2`
Expected: PASS.

- [x] **Step 7: Lint and commit**

```bash
.venv/bin/python -m flake8 web/constants.py dashboard/forms.py dashboard/tests/test_member_forms.py
git add web/constants.py dashboard/forms.py dashboard/tests/test_member_forms.py
git commit -m "feat(dashboard): member and membership-term forms

Tier choices come from web.constants.MEMBERSHIP at the form layer, which
is the only place allowed to bridge the two: web imports audience, so the
models cannot import the catalogue back.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01J5vdXGkpYi5e5hYvdUDtAW"
```

---

### Task 6: The roster page

Read-only list first: URL, view, template, sidebar link, CSS. Create/edit/delete arrive in Task 7, so this task's deliverable is a page that shows who your members are.

**Files:**
- Create: `dashboard/member_views.py`
- Create: `dashboard/templates/dashboard/members.html`
- Create: `dashboard/templates/dashboard/_member_list.html`
- Create: `dashboard/static/dashboard/css/members.css`
- Modify: `dashboard/urls.py`
- Modify: `dashboard/templates/dashboard/_sidebar.html`
- Test: `dashboard/tests/test_members.py`

**Interfaces:**
- Consumes: `Member` and its `status` / `current_term` (Task 4); `MEMBERSHIP_TIER_LABELS` (Task 5)
- Produces:
  - URL names `dashboard:members`
  - `MemberListView`, and the module-level helper `member_roster(request)` returning the filtered queryset — Task 7 and Task 9 reuse it
  - Template block `<div id="member-list">` — Task 7 swaps it out of band

- [x] **Step 1: Write the failing tests**

Create `dashboard/tests/test_members.py`:

```python
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audience.models import Member, MembershipTerm

User = get_user_model()


def make_member(first="Ada", last="Lovelace", email="ada@example.com", **kwargs):
    return Member.objects.create(
        first_name=first, last_name=last, email=email, **kwargs
    )


def give_term(member, days_left=100, tier="individual"):
    today = timezone.localdate()
    return MembershipTerm.objects.create(
        member=member,
        tier=tier,
        started_on=today - datetime.timedelta(days=30),
        expires_on=today + datetime.timedelta(days=days_left),
        price_paid=Decimal("60.00"),
    )


class MemberListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("empty-state", html)
        self.assertIn("No Members Yet", html)

    def test_rows_show_name_email_tier_and_expiry(self) -> None:
        member = make_member()
        give_term(member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("Lovelace", html)
        self.assertIn("ada@example.com", html)
        self.assertIn("Individual", html)  # tier label, not the slug

    def test_status_pills(self) -> None:
        give_term(make_member(email="a@example.com"), days_left=200)
        give_term(make_member("Soon", "Expiring", "b@example.com"), days_left=5)
        make_member("No", "Terms", "c@example.com")
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("Active", html)
        self.assertIn("Expiring soon", html)
        self.assertIn("Lapsed", html)

    def test_query_filter_matches_name_and_email(self) -> None:
        give_term(make_member("Ada", "Lovelace", "ada@example.com"))
        give_term(make_member("Grace", "Hopper", "grace@example.com"))

        by_name = self.client.get(
            reverse("dashboard:members"), {"q": "hopper"}
        ).content.decode()
        self.assertIn("Hopper", by_name)
        self.assertNotIn("Lovelace", by_name)

        by_email = self.client.get(
            reverse("dashboard:members"), {"q": "ada@"}
        ).content.decode()
        self.assertIn("Lovelace", by_email)
        self.assertNotIn("Hopper", by_email)

    def test_status_filter(self) -> None:
        give_term(make_member("Cur", "Rent", "current@example.com"))
        make_member("No", "Terms", "never@example.com")

        active = self.client.get(
            reverse("dashboard:members"), {"status": "active"}
        ).content.decode()
        self.assertIn("Rent", active)
        self.assertNotIn("Terms", active)

        lapsed = self.client.get(
            reverse("dashboard:members"), {"status": "lapsed"}
        ).content.decode()
        self.assertIn("Terms", lapsed)
        self.assertNotIn("Rent", lapsed)

    def test_unknown_status_filter_is_ignored(self) -> None:
        give_term(make_member())
        html = self.client.get(
            reverse("dashboard:members"), {"status": "nonsense"}
        ).content.decode()
        self.assertIn("Lovelace", html)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:members")).status_code, 302
        )
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(
            self.client.get(reverse("dashboard:members")).status_code, 403
        )

    def test_members_css_linked(self) -> None:
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("dashboard/css/members.css", html)

    def test_sidebar_links_to_members(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(reverse("dashboard:members"), html)
```

- [x] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_members -v 2`
Expected: FAIL — `NoReverseMatch: 'members' is not a valid view function or pattern name`.

- [x] **Step 3: Write the view module**

Create `dashboard/member_views.py`:

```python
"""Staff surface for the membership roster.

Replaces a spreadsheet. Memberships are still sold through Square payment
links; nothing here talks to Square, and nothing here is public — members
are the first real customer PII in this database, so every view is
staff-only, the CSV export included.
"""

from audience.models import Member
from django.db import models
from django.shortcuts import render
from django.views import View
from web.constants import MEMBERSHIP_TIER_LABELS

from .mixins import StaffRequiredMixin

STATUS_FILTERS = [
    ("", "All members"),
    ("active", "Active"),
    ("expiring", "Expiring soon"),
    ("lapsed", "Lapsed"),
]


def member_roster(request):
    """The roster as filtered by ?q= and ?status=.

    Status is derived from dates rather than stored, so the status filter
    runs in Python over the prefetched terms. The roster is a few hundred
    rows at most; a query that could express "expiring soon" in SQL would
    duplicate the definition that lives on the model.
    """
    members = Member.objects.prefetch_related("terms")

    q = (request.GET.get("q") or "").strip()
    if q:
        members = members.filter(
            models.Q(first_name__icontains=q)
            | models.Q(last_name__icontains=q)
            | models.Q(email__icontains=q)
        )

    status = (request.GET.get("status") or "").strip()
    valid = {value for value, _label in STATUS_FILTERS if value}
    members = list(members)
    if status in valid:
        members = [m for m in members if m.status == status]
    return members, q, status


class MemberListView(StaffRequiredMixin, View):
    def get(self, request):
        members, q, status = member_roster(request)
        return render(
            request,
            "dashboard/members.html",
            {
                "members": members,
                "q": q,
                "selected_status": status,
                "statuses": STATUS_FILTERS,
                "tier_labels": MEMBERSHIP_TIER_LABELS,
                "active_count": Member.objects.active().count(),
            },
        )
```

Add `from django.db import models` to the imports — `member_roster` uses `models.Q`.

- [x] **Step 4: Write the templates**

Create `dashboard/templates/dashboard/members.html`:

```html
{% extends "dashboard/base_dashboard.html" %}
{% load static %}
{% block title %}Members · LeprinceOS{% endblock %}
{% block head_extra %}<link rel="stylesheet" href="{% static 'dashboard/css/members.css' %}" />{% endblock %}
{% block content %}
<div class="page">
  <div class="header">
    <div>
      <h1 class="title">Members</h1>
      <p class="subtitle">{{ active_count }} active member{{ active_count|pluralize }}.</p>
    </div>
  </div>

  <form class="memberFilters" method="get" action="{% url 'dashboard:members' %}">
    <input class="input" type="search" name="q" value="{{ q }}" placeholder="Search name or email" />
    <select class="input" name="status">
      {% for value, label in statuses %}
      <option value="{{ value }}" {% if value == selected_status %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <button class="actionButton" type="submit">Filter</button>
  </form>

  {% include "dashboard/_member_list.html" %}
</div>
{% endblock %}
```

Create `dashboard/templates/dashboard/_member_list.html`:

```html
{% load dashboard_extras %}
<div id="member-list">
  {% if members %}
  <div class="tableWrapper">
    <table class="table">
      <thead>
        <tr><th>Name</th><th>Email</th><th>Phone</th><th>Tier</th><th>Expires</th><th>Status</th></tr>
      </thead>
      <tbody>
        {% for member in members %}
        <tr>
          <td class="memberName">{{ member.last_name }}, {{ member.first_name }}</td>
          <td>{{ member.email }}</td>
          <td>{{ member.phone|default:"—" }}</td>
          <td>{% if member.current_term %}{{ tier_labels|get_item:member.current_term.tier }}{% else %}—{% endif %}</td>
          <td>{% if member.current_term %}{{ member.current_term.expires_on|date:"M j, Y" }}{% else %}—{% endif %}</td>
          <td><span class="statusPill status-{{ member.status }}">{{ member.status_label }}</span></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="empty-state">
    <div class="empty-state-icon" style="font-size: 2.5rem;">🎟️</div>
    <h3 class="empty-state-title">No Members Yet</h3>
    <p class="empty-state-description">Memberships sold through Square are recorded here by hand. Add the roster as people join or renew.</p>
  </div>
  {% endif %}
</div>
```

Note: the name cell is deliberately plain text here. `dashboard:member_detail` does not exist until Task 8, and `{% url %}` on an unknown name raises `NoReverseMatch` at render time — Task 8 replaces this cell with the anchor once the view exists.

- [x] **Step 5: Write the CSS**

Create `dashboard/static/dashboard/css/members.css`:

```css
.memberFilters {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.memberFilters .input {
  max-width: 18rem;
}

.statusPill {
  display: inline-block;
  padding: 0.15rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
}

.statusPill.status-active {
  background: rgba(34, 139, 94, 0.15);
  color: #1c7a52;
}

.statusPill.status-expiring {
  background: rgba(196, 143, 44, 0.18);
  color: #8a6111;
}

.statusPill.status-lapsed {
  background: rgba(120, 120, 120, 0.15);
  color: #5b5b5b;
}

.memberLink {
  color: inherit;
  font-weight: 600;
  text-decoration: none;
}

.memberLink:hover {
  text-decoration: underline;
}
```

- [x] **Step 6: Wire the URL**

In `dashboard/urls.py`, add `member_views` to the `from . import ...` line and add this entry after the `subscribers` block:

```python
    path("members", member_views.MemberListView.as_view(), name="members"),
```

- [x] **Step 7: Add the sidebar link**

In `dashboard/templates/dashboard/_sidebar.html`, between the Subscribers and Inquiries links:

```html
    <a href="{% url 'dashboard:members' %}" class="sidebarLink {% nav_active request 'dashboard:members' %}" @click="sidebarOpen = false">
      <svg class="sidebarIcon" width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="5" width="16" height="11" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M2 9h16" stroke="currentColor" stroke-width="1.5"/><path d="M5 13h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>Members</a>
```

- [x] **Step 8: Run the tests**

Run: `.venv/bin/python manage.py test dashboard.tests.test_members -v 2`
Expected: PASS, 9 tests.

- [x] **Step 9: Run the whole dashboard suite — the sidebar is on every page**

Run: `.venv/bin/python manage.py test dashboard -v 2`
Expected: PASS.

- [x] **Step 10: Lint and commit**

```bash
.venv/bin/python -m flake8 dashboard
git add dashboard
git commit -m "feat(dashboard): membership roster page

Search by name or email, filter by derived status. Read-only for now;
editing lands next.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01J5vdXGkpYi5e5hYvdUDtAW"
```

---

### Task 7: Add, edit, and delete members

Mirrors `ScreenCreateView` / `ScreenEditView` / `ScreenDeleteView` in `dashboard/views.py:149-195`, including the out-of-band list swap and the `HX-Trigger` toast. Unlike Screens, delete is **not** protected — a person entered by mistake should be removable, and their terms exist only to describe them.

**Files:**
- Modify: `dashboard/member_views.py`
- Create: `dashboard/templates/dashboard/_member_form.html`
- Modify: `dashboard/templates/dashboard/members.html` (New Member button)
- Modify: `dashboard/templates/dashboard/_member_list.html` (row actions)
- Modify: `dashboard/urls.py`
- Test: `dashboard/tests/test_members.py` (append)

**Interfaces:**
- Consumes: `MemberForm` (Task 5); `member_roster` (Task 6)
- Produces: URL names `dashboard:member_create`, `dashboard:member_edit`, `dashboard:member_delete`; helpers `_render_member_form(request, form, action_url, submit_label)` and `_member_list_response(request, toast_message)` — Task 8 reuses neither, but Task 9 relies on the list markup staying stable

- [x] **Step 1: Write the failing tests**

Append to `dashboard/tests/test_members.py`:

```python
import json


class MemberCreateEditTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_get_create_form(self) -> None:
        html = self.client.get(reverse("dashboard:member_create")).content.decode()
        self.assertIn('id="member-form"', html)
        self.assertIn("Add Member", html)

    def test_post_create_valid(self) -> None:
        resp = self.client.post(
            reverse("dashboard:member_create"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "Ada@Example.com",
                "phone": "",
                "notes": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        member = Member.objects.get()
        self.assertEqual(member.email, "ada@example.com")

        triggers = json.loads(resp["HX-Trigger"])
        self.assertTrue(triggers["close-drawer"])
        self.assertEqual(triggers["dashboard-toast"]["kind"], "success")
        self.assertIn('hx-swap-oob="true"', resp.content.decode())

    def test_post_create_invalid_redisplays_the_form(self) -> None:
        resp = self.client.post(
            reverse("dashboard:member_create"),
            {"first_name": "Ada", "last_name": "Lovelace", "email": "not-an-email"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="member-form"', resp.content.decode())
        self.assertEqual(Member.objects.count(), 0)

    def test_post_edit_updates(self) -> None:
        member = make_member()
        self.client.post(
            reverse("dashboard:member_edit", args=[member.pk]),
            {
                "first_name": "Ada",
                "last_name": "King",
                "email": "ada@example.com",
                "phone": "207-555-0100",
                "notes": "",
            },
        )
        member.refresh_from_db()
        self.assertEqual(member.last_name, "King")
        self.assertEqual(member.phone, "207-555-0100")

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:member_create")).status_code, 302
        )


class MemberDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_delete_removes_the_member_and_their_terms(self) -> None:
        member = make_member()
        give_term(member)
        resp = self.client.post(reverse("dashboard:member_delete", args=[member.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Member.objects.count(), 0)
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_delete_toasts(self) -> None:
        member = make_member()
        resp = self.client.post(reverse("dashboard:member_delete", args=[member.pk]))
        triggers = json.loads(resp["HX-Trigger"])
        self.assertEqual(triggers["dashboard-toast"]["kind"], "success")

    def test_confirm_copy_names_the_term_count(self) -> None:
        member = make_member()
        give_term(member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("1 membership term", html)
```

- [x] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_members -v 2`
Expected: FAIL — `NoReverseMatch: 'member_create'`.

- [x] **Step 3: Add the view helpers and the three views**

Append to `dashboard/member_views.py` (add `import json`, `from django.http import HttpResponse`, `from django.shortcuts import get_object_or_404, render`, `from django.urls import reverse`, and `from .forms import MemberForm` to the imports):

```python
def _render_member_form(request, form, action_url, submit_label):
    return render(
        request,
        "dashboard/_member_form.html",
        {"form": form, "form_action": action_url, "submit_label": submit_label},
    )


def _member_list_response(request, toast_message):
    """Success response: OOB-swap the list, close the drawer, and toast."""
    members, q, status = member_roster(request)
    html = render(
        request,
        "dashboard/_member_list.html",
        {"members": members, "tier_labels": MEMBERSHIP_TIER_LABELS},
    ).content.decode()
    html = html.replace(
        '<div id="member-list">', '<div id="member-list" hx-swap-oob="true">', 1
    )
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps(
        {
            "close-drawer": True,
            "dashboard-toast": {"kind": "success", "message": toast_message},
        }
    )
    return resp


class MemberCreateView(StaffRequiredMixin, View):
    def get(self, request):
        return _render_member_form(
            request, MemberForm(), reverse("dashboard:member_create"), "Add Member"
        )

    def post(self, request):
        form = MemberForm(request.POST)
        if form.is_valid():
            form.save()
            return _member_list_response(request, "Member added")
        return _render_member_form(
            request, form, reverse("dashboard:member_create"), "Add Member"
        )


class MemberEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        return _render_member_form(
            request,
            MemberForm(instance=member),
            reverse("dashboard:member_edit", args=[pk]),
            "Save Changes",
        )

    def post(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        form = MemberForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            return _member_list_response(request, "Member updated")
        return _render_member_form(
            request,
            form,
            reverse("dashboard:member_edit", args=[pk]),
            "Save Changes",
        )


class MemberDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        # No ProtectedError guard, unlike Screens: a person entered by
        # mistake should be removable, and their terms only describe them.
        get_object_or_404(Member, pk=pk).delete()
        return _member_list_response(request, "Member deleted")
```

- [x] **Step 4: Write the form partial**

Create `dashboard/templates/dashboard/_member_form.html`:

```html
<form id="member-form" class="form" hx-post="{{ form_action }}" hx-target="#drawer-content" hx-swap="innerHTML">
  {% csrf_token %}
  {% if form.non_field_errors %}<div class="field-error">{{ form.non_field_errors }}</div>{% endif %}
  <div class="formRow">
    <div class="formGroup">
      <label for="{{ form.first_name.id_for_label }}">First Name</label>
      {{ form.first_name }}
      {% if form.first_name.errors %}<div class="field-error">{{ form.first_name.errors|striptags }}</div>{% endif %}
    </div>
    <div class="formGroup">
      <label for="{{ form.last_name.id_for_label }}">Last Name</label>
      {{ form.last_name }}
      {% if form.last_name.errors %}<div class="field-error">{{ form.last_name.errors|striptags }}</div>{% endif %}
    </div>
  </div>
  <div class="formRow">
    <div class="formGroup">
      <label for="{{ form.email.id_for_label }}">Email</label>
      {{ form.email }}
      {% if form.email.errors %}<div class="field-error">{{ form.email.errors|striptags }}</div>{% endif %}
    </div>
    <div class="formGroup">
      <label for="{{ form.phone.id_for_label }}">Phone</label>
      {{ form.phone }}
    </div>
  </div>
  <div class="formRow">
    <div class="formGroup">
      <label for="{{ form.notes.id_for_label }}">Notes</label>
      {{ form.notes }}
    </div>
  </div>
</form>
<div id="drawer-footer" class="footer" hx-swap-oob="true">
  <button type="button" class="cancelButton" @click="$store.drawer.close()">Cancel</button>
  <button type="submit" form="member-form" class="submitButton">{{ submit_label }}</button>
</div>
```

- [x] **Step 5: Add the New Member button**

In `dashboard/templates/dashboard/members.html`, inside `<div class="header">` after the `<div>` holding the title:

```html
    <button class="primaryButton" hx-get="{% url 'dashboard:member_create' %}"
            hx-target="#drawer-content" @click="$store.drawer.show('New Member')">+ New Member</button>
```

Also add the same button to the empty state in `_member_list.html`, replacing the closing `</div>` of `.empty-state`:

```html
    <button class="btn btn-primary" hx-get="{% url 'dashboard:member_create' %}"
            hx-target="#drawer-content" @click="$store.drawer.show('New Member')">Add First Member</button>
  </div>
```

- [x] **Step 6: Add the row actions**

In `_member_list.html`, add `<th>Actions</th>` to the header row and this cell to each body row:

```html
          <td>
            <div class="actions">
              <button class="actionButton" hx-get="{% url 'dashboard:member_edit' member.pk %}"
                      hx-target="#drawer-content" @click="$store.drawer.show('Edit Member')">Edit</button>
              <button class="actionButton deleteButton"
                      hx-post="{% url 'dashboard:member_delete' member.pk %}"
                      hx-target="#member-list" hx-swap="outerHTML"
                      data-dashboard-confirm='{"title":"Delete Member","message":"Delete {{ member.full_name|escapejs }} and their {{ member.terms.count }} membership term(s)? This cannot be undone.","confirmLabel":"Delete","variant":"danger"}'>Delete</button>
            </div>
          </td>
```

- [x] **Step 7: Wire the URLs**

In `dashboard/urls.py`, after the `members` entry:

```python
    path("members/new", member_views.MemberCreateView.as_view(), name="member_create"),
    path("members/<int:pk>/edit", member_views.MemberEditView.as_view(), name="member_edit"),
    path("members/<int:pk>/delete", member_views.MemberDeleteView.as_view(), name="member_delete"),
```

- [x] **Step 8: Run the tests**

Run: `.venv/bin/python manage.py test dashboard.tests.test_members -v 2`
Expected: PASS, 17 tests (9 from Task 6, 5 create/edit, 3 delete).

- [x] **Step 9: Lint and commit**

```bash
.venv/bin/python -m flake8 dashboard
git add dashboard
git commit -m "feat(dashboard): add, edit and delete members

Drawer form and OOB list swap, matching the Screens pattern. Delete
confirms rather than protects: a mistaken entry should be removable.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01J5vdXGkpYi5e5hYvdUDtAW"
```

---

### Task 8: Member detail and the renewal workflow

Terms do not fit on a list row, so they live on the member's page. This is the renewal path: open the person, add a term, and last year's term stays visible above it.

**Files:**
- Modify: `dashboard/member_views.py`
- Create: `dashboard/templates/dashboard/member_detail.html`
- Create: `dashboard/templates/dashboard/_term_list.html`
- Create: `dashboard/templates/dashboard/_term_form.html`
- Modify: `dashboard/templates/dashboard/_member_list.html` (link the name)
- Modify: `dashboard/urls.py`
- Test: `dashboard/tests/test_member_terms.py`

**Interfaces:**
- Consumes: `MembershipTermForm` (Task 5); `Member`, `MembershipTerm` (Tasks 3-4)
- Produces: URL names `dashboard:member_detail`, `dashboard:term_create`, `dashboard:term_edit`, `dashboard:term_delete`; `<div id="term-list">` for the OOB swap

- [x] **Step 1: Write the failing tests**

Create `dashboard/tests/test_member_terms.py`:

```python
import datetime
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audience.models import Member, MembershipTerm

User = get_user_model()


class MemberDetailTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.member = Member.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="207-555-0100",
        )

    def test_shows_contact_details(self) -> None:
        html = self.client.get(
            reverse("dashboard:member_detail", args=[self.member.pk])
        ).content.decode()
        self.assertIn("Ada Lovelace", html)
        self.assertIn("ada@example.com", html)
        self.assertIn("207-555-0100", html)

    def test_lists_terms_newest_first_with_tier_labels(self) -> None:
        MembershipTerm.objects.create(
            member=self.member, tier="individual",
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2026, 1, 1), price_paid=Decimal("60.00"),
        )
        MembershipTerm.objects.create(
            member=self.member, tier="cinema-supporter",
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2027, 1, 1), price_paid=Decimal("120.00"),
        )
        html = self.client.get(
            reverse("dashboard:member_detail", args=[self.member.pk])
        ).content.decode()
        self.assertLess(html.index("Cinema Supporter"), html.index("Individual"))

    def test_empty_terms_state(self) -> None:
        html = self.client.get(
            reverse("dashboard:member_detail", args=[self.member.pk])
        ).content.decode()
        self.assertIn("No membership terms yet", html)

    def test_missing_member_is_404(self) -> None:
        self.assertEqual(
            self.client.get(
                reverse("dashboard:member_detail", args=[99999])
            ).status_code,
            404,
        )

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(
                reverse("dashboard:member_detail", args=[self.member.pk])
            ).status_code,
            302,
        )


class TermCreateTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )

    def test_get_form(self) -> None:
        html = self.client.get(
            reverse("dashboard:term_create", args=[self.member.pk])
        ).content.decode()
        self.assertIn('id="term-form"', html)
        self.assertIn("Add Term", html)

    def test_renewal_needs_only_a_tier_and_a_start_date(self) -> None:
        resp = self.client.post(
            reverse("dashboard:term_create", args=[self.member.pk]),
            {"tier": "individual", "started_on": "2026-09-11",
             "expires_on": "", "price_paid": "", "purchased_at": "", "notes": ""},
        )
        self.assertEqual(resp.status_code, 200)
        term = MembershipTerm.objects.get()
        self.assertEqual(term.member, self.member)
        self.assertEqual(term.expires_on, datetime.date(2027, 9, 11))
        self.assertEqual(term.price_paid, Decimal("60.00"))

        triggers = json.loads(resp["HX-Trigger"])
        self.assertEqual(triggers["dashboard-toast"]["kind"], "success")

    def test_invalid_tier_redisplays_the_form(self) -> None:
        resp = self.client.post(
            reverse("dashboard:term_create", args=[self.member.pk]),
            {"tier": "invented", "started_on": "2026-09-11"},
        )
        self.assertIn('id="term-form"', resp.content.decode())
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_a_second_term_makes_a_lapsed_member_active(self) -> None:
        today = timezone.localdate()
        MembershipTerm.objects.create(
            member=self.member, tier="individual",
            started_on=today - datetime.timedelta(days=800),
            expires_on=today - datetime.timedelta(days=400),
            price_paid=Decimal("60.00"),
        )
        self.assertFalse(self.member.is_active)

        self.client.post(
            reverse("dashboard:term_create", args=[self.member.pk]),
            {"tier": "individual", "started_on": today.isoformat(),
             "expires_on": "", "price_paid": "", "purchased_at": "", "notes": ""},
        )
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)
        self.assertEqual(self.member.terms.count(), 2)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(
                reverse("dashboard:term_create", args=[self.member.pk])
            ).status_code,
            302,
        )


class TermEditDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        self.term = MembershipTerm.objects.create(
            member=self.member, tier="individual",
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2027, 1, 1), price_paid=Decimal("60.00"),
        )

    def test_edit_fixes_a_typo(self) -> None:
        self.client.post(
            reverse("dashboard:term_edit", args=[self.term.pk]),
            {"tier": "individual", "started_on": "2026-01-02",
             "expires_on": "2027-01-02", "price_paid": "60.00",
             "purchased_at": "", "notes": ""},
        )
        self.term.refresh_from_db()
        self.assertEqual(self.term.started_on, datetime.date(2026, 1, 2))

    def test_edit_cannot_move_a_term_to_another_member(self) -> None:
        other = Member.objects.create(
            first_name="Grace", last_name="Hopper", email="grace@example.com"
        )
        self.client.post(
            reverse("dashboard:term_edit", args=[self.term.pk]),
            {"tier": "individual", "started_on": "2026-01-01",
             "expires_on": "2027-01-01", "price_paid": "60.00",
             "purchased_at": "", "notes": "", "member": other.pk},
        )
        self.term.refresh_from_db()
        self.assertEqual(self.term.member, self.member)

    def test_delete_removes_only_that_term(self) -> None:
        MembershipTerm.objects.create(
            member=self.member, tier="individual",
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2026, 1, 1), price_paid=Decimal("60.00"),
        )
        self.client.post(reverse("dashboard:term_delete", args=[self.term.pk]))
        self.assertEqual(self.member.terms.count(), 1)
        self.assertEqual(Member.objects.count(), 1)
```

- [x] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_member_terms -v 2`
Expected: FAIL — `NoReverseMatch: 'member_detail'`.

- [x] **Step 3: Add the detail and term views**

Append to `dashboard/member_views.py` (add `from audience.models import Member, MembershipTerm` and `from .forms import MemberForm, MembershipTermForm` — fold into the existing import lines):

```python
def _render_term_form(request, form, action_url, submit_label):
    return render(
        request,
        "dashboard/_term_form.html",
        {"form": form, "form_action": action_url, "submit_label": submit_label},
    )


def _term_list_response(request, member, toast_message):
    """OOB-swap the member's term list, close the drawer, and toast."""
    html = render(
        request,
        "dashboard/_term_list.html",
        {
            "member": member,
            "terms": member.terms.all(),
            "tier_labels": MEMBERSHIP_TIER_LABELS,
        },
    ).content.decode()
    html = html.replace(
        '<div id="term-list">', '<div id="term-list" hx-swap-oob="true">', 1
    )
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps(
        {
            "close-drawer": True,
            "dashboard-toast": {"kind": "success", "message": toast_message},
        }
    )
    return resp


class MemberDetailView(StaffRequiredMixin, View):
    def get(self, request, pk):
        member = get_object_or_404(
            Member.objects.prefetch_related("terms"), pk=pk
        )
        return render(
            request,
            "dashboard/member_detail.html",
            {
                "member": member,
                "terms": member.terms.all(),
                "tier_labels": MEMBERSHIP_TIER_LABELS,
            },
        )


class TermCreateView(StaffRequiredMixin, View):
    def get(self, request, pk):
        get_object_or_404(Member, pk=pk)
        return _render_term_form(
            request,
            MembershipTermForm(),
            reverse("dashboard:term_create", args=[pk]),
            "Add Term",
        )

    def post(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        form = MembershipTermForm(request.POST)
        if form.is_valid():
            term = form.save(commit=False)
            # The member comes from the URL, never the payload.
            term.member = member
            term.save()
            return _term_list_response(request, member, "Term added")
        return _render_term_form(
            request,
            form,
            reverse("dashboard:term_create", args=[pk]),
            "Add Term",
        )


class TermEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        term = get_object_or_404(MembershipTerm, pk=pk)
        return _render_term_form(
            request,
            MembershipTermForm(instance=term),
            reverse("dashboard:term_edit", args=[pk]),
            "Save Changes",
        )

    def post(self, request, pk):
        term = get_object_or_404(MembershipTerm, pk=pk)
        form = MembershipTermForm(request.POST, instance=term)
        if form.is_valid():
            # `member` is not a form field, so a posted member id is ignored.
            form.save()
            return _term_list_response(request, term.member, "Term updated")
        return _render_term_form(
            request,
            form,
            reverse("dashboard:term_edit", args=[pk]),
            "Save Changes",
        )


class TermDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        term = get_object_or_404(MembershipTerm, pk=pk)
        member = term.member
        term.delete()
        return _term_list_response(request, member, "Term deleted")
```

- [x] **Step 4: Write the detail templates**

Create `dashboard/templates/dashboard/member_detail.html`:

```html
{% extends "dashboard/base_dashboard.html" %}
{% load static %}
{% block title %}{{ member.full_name }} · LeprinceOS{% endblock %}
{% block head_extra %}<link rel="stylesheet" href="{% static 'dashboard/css/members.css' %}" />{% endblock %}
{% block content %}
<div class="page">
  <div class="header">
    <div>
      <a class="backLink" href="{% url 'dashboard:members' %}">← Members</a>
      <h1 class="title">{{ member.full_name }}</h1>
      <p class="subtitle">
        <span class="statusPill status-{{ member.status }}">{{ member.status_label }}</span>
        {{ member.email }}{% if member.phone %} · {{ member.phone }}{% endif %}
      </p>
    </div>
    <button class="primaryButton" hx-get="{% url 'dashboard:term_create' member.pk %}"
            hx-target="#drawer-content" @click="$store.drawer.show('Add Term')">+ Add Term</button>
  </div>

  {% if member.notes %}<p class="memberNotes">{{ member.notes|linebreaksbr }}</p>{% endif %}

  {% include "dashboard/_term_list.html" %}
</div>
{% endblock %}
```

Create `dashboard/templates/dashboard/_term_list.html`:

```html
{% load dashboard_extras %}
<div id="term-list">
  {% if terms %}
  <div class="tableWrapper">
    <table class="table">
      <thead>
        <tr><th>Tier</th><th>Started</th><th>Expires</th><th>Paid</th><th>Purchased</th><th>Actions</th></tr>
      </thead>
      <tbody>
        {% for term in terms %}
        <tr class="{% if term.is_current %}currentTerm{% endif %}">
          <td>{{ tier_labels|get_item:term.tier }}</td>
          <td>{{ term.started_on|date:"M j, Y" }}</td>
          <td>{{ term.expires_on|date:"M j, Y" }}</td>
          <td>${{ term.price_paid }}</td>
          <td>{{ term.purchased_at|date:"M j, Y"|default:"—" }}</td>
          <td>
            <div class="actions">
              <button class="actionButton" hx-get="{% url 'dashboard:term_edit' term.pk %}"
                      hx-target="#drawer-content" @click="$store.drawer.show('Edit Term')">Edit</button>
              <button class="actionButton deleteButton"
                      hx-post="{% url 'dashboard:term_delete' term.pk %}"
                      hx-target="#term-list" hx-swap="outerHTML"
                      data-dashboard-confirm='{"title":"Delete Term","message":"Delete this membership term? This cannot be undone.","confirmLabel":"Delete","variant":"danger"}'>Delete</button>
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="empty-state">
    <h3 class="empty-state-title">No membership terms yet</h3>
    <p class="empty-state-description">Add a term when this person buys or renews a membership.</p>
  </div>
  {% endif %}
</div>
```

Create `dashboard/templates/dashboard/_term_form.html`:

```html
<form id="term-form" class="form" hx-post="{{ form_action }}" hx-target="#drawer-content" hx-swap="innerHTML">
  {% csrf_token %}
  {% if form.non_field_errors %}<div class="field-error">{{ form.non_field_errors }}</div>{% endif %}
  <div class="formRow">
    <div class="formGroup">
      <label for="{{ form.tier.id_for_label }}">Tier</label>
      {{ form.tier }}
      {% if form.tier.errors %}<div class="field-error">{{ form.tier.errors|striptags }}</div>{% endif %}
    </div>
    <div class="formGroup">
      <label for="{{ form.started_on.id_for_label }}">Start Date</label>
      {{ form.started_on }}
      {% if form.started_on.errors %}<div class="field-error">{{ form.started_on.errors|striptags }}</div>{% endif %}
    </div>
  </div>
  <div class="formRow">
    <div class="formGroup">
      <label for="{{ form.expires_on.id_for_label }}">Expires (inclusive)</label>
      {{ form.expires_on }}
      <p class="fieldHint">Leave blank for the tier's usual length.</p>
      {% if form.expires_on.errors %}<div class="field-error">{{ form.expires_on.errors|striptags }}</div>{% endif %}
    </div>
    <div class="formGroup">
      <label for="{{ form.price_paid.id_for_label }}">Price Paid</label>
      {{ form.price_paid }}
      <p class="fieldHint">Leave blank for the tier's list price.</p>
      {% if form.price_paid.errors %}<div class="field-error">{{ form.price_paid.errors|striptags }}</div>{% endif %}
    </div>
  </div>
  <div class="formRow">
    <div class="formGroup">
      <label for="{{ form.purchased_at.id_for_label }}">Purchased On</label>
      {{ form.purchased_at }}
    </div>
    <div class="formGroup">
      <label for="{{ form.notes.id_for_label }}">Notes</label>
      {{ form.notes }}
    </div>
  </div>
</form>
<div id="drawer-footer" class="footer" hx-swap-oob="true">
  <button type="button" class="cancelButton" @click="$store.drawer.close()">Cancel</button>
  <button type="submit" form="term-form" class="submitButton">{{ submit_label }}</button>
</div>
```

- [x] **Step 5: Link the roster rows to the detail page**

In `_member_list.html`, replace the plain-text name cell from Task 6 — the line reading `<td class="memberName">{{ member.last_name }}, {{ member.first_name }}</td>` — with:

```html
          <td><a class="memberLink" href="{% url 'dashboard:member_detail' member.pk %}">{{ member.last_name }}, {{ member.first_name }}</a></td>
```

- [x] **Step 6: Add the supporting CSS**

Append to `dashboard/static/dashboard/css/members.css`:

```css
.backLink {
  display: inline-block;
  margin-bottom: 0.35rem;
  font-size: 0.85rem;
  color: inherit;
  opacity: 0.7;
  text-decoration: none;
}

.backLink:hover {
  opacity: 1;
}

.memberNotes {
  margin: 0 0 1rem;
  white-space: pre-wrap;
  opacity: 0.85;
}

.fieldHint {
  margin: 0.25rem 0 0;
  font-size: 0.75rem;
  opacity: 0.7;
}

tr.currentTerm td {
  font-weight: 600;
}
```

- [x] **Step 7: Wire the URLs**

In `dashboard/urls.py`, after the member entries:

```python
    path("members/<int:pk>", member_views.MemberDetailView.as_view(), name="member_detail"),
    path("members/<int:pk>/terms/new", member_views.TermCreateView.as_view(), name="term_create"),
    path("terms/<int:pk>/edit", member_views.TermEditView.as_view(), name="term_edit"),
    path("terms/<int:pk>/delete", member_views.TermDeleteView.as_view(), name="term_delete"),
```

`members/<int:pk>` must come **after** `members/new`, or `new` would be matched as a pk. It will not — `<int:pk>` does not match `new` — but keep the order anyway for readability.

- [x] **Step 8: Run the tests**

Run: `.venv/bin/python manage.py test dashboard -v 2`
Expected: PASS.

- [x] **Step 9: Lint and commit**

```bash
.venv/bin/python -m flake8 dashboard
git add dashboard
git commit -m "feat(dashboard): member detail page and the renewal workflow

Open the person, add a term; last year's term stays visible above it.
The member comes from the URL, never the posted payload.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01J5vdXGkpYi5e5hYvdUDtAW"
```

---

### Task 9: CSV export

One row per member drawn from their most recent term — the shape of the spreadsheet being replaced. Honours the roster's current `?q=` and `?status=` filters, so "export the lapsed members" is just filtering and clicking Export.

**Files:**
- Modify: `dashboard/member_views.py`
- Modify: `dashboard/templates/dashboard/members.html` (Export button)
- Modify: `dashboard/urls.py`
- Test: `dashboard/tests/test_members.py` (append)

**Interfaces:**
- Consumes: `member_roster` (Task 6)
- Produces: URL name `dashboard:members_export`

- [x] **Step 1: Write the failing tests**

Append to `dashboard/tests/test_members.py`:

```python
class MemberExportTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_export_is_a_csv_attachment(self) -> None:
        resp = self.client.get(reverse("dashboard:members_export"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertIn("members.csv", resp["Content-Disposition"])

    def test_header_row(self) -> None:
        body = self.client.get(reverse("dashboard:members_export")).content.decode()
        self.assertTrue(
            body.startswith(
                "first_name,last_name,email,phone,tier,started_on,"
                "expires_on,price_paid,status"
            )
        )

    def test_one_row_per_member_from_the_latest_term(self) -> None:
        member = make_member()
        MembershipTerm.objects.create(
            member=member, tier="individual",
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2026, 1, 1), price_paid=Decimal("60.00"),
        )
        give_term(member, tier="cinema-supporter")  # newer

        rows = [
            r for r in self.client.get(
                reverse("dashboard:members_export")
            ).content.decode().splitlines() if r
        ]
        self.assertEqual(len(rows), 2)  # header + one member
        self.assertIn("cinema-supporter", rows[1])
        self.assertNotIn("individual", rows[1])

    def test_a_member_with_no_terms_still_exports(self) -> None:
        make_member("No", "Terms", "never@example.com")
        rows = [
            r for r in self.client.get(
                reverse("dashboard:members_export")
            ).content.decode().splitlines() if r
        ]
        self.assertEqual(len(rows), 2)
        self.assertIn("lapsed", rows[1])

    def test_export_honours_the_status_filter(self) -> None:
        give_term(make_member("Cur", "Rent", "current@example.com"))
        make_member("No", "Terms", "never@example.com")
        body = self.client.get(
            reverse("dashboard:members_export"), {"status": "lapsed"}
        ).content.decode()
        self.assertIn("never@example.com", body)
        self.assertNotIn("current@example.com", body)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:members_export")).status_code, 302
        )
```

- [x] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_members -v 2`
Expected: FAIL — `NoReverseMatch: 'members_export'`.

- [x] **Step 3: Write the export view**

Append to `dashboard/member_views.py` (add `import csv` to the imports):

```python
class MemberExportView(StaffRequiredMixin, View):
    """One row per member, from their most recent term.

    Matches the shape of the spreadsheet this replaces. A per-term export
    for revenue analysis would be a second view; this one answers "who are
    my members".
    """

    def get(self, request):
        members, _q, _status = member_roster(request)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="members.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "first_name", "last_name", "email", "phone",
            "tier", "started_on", "expires_on", "price_paid", "status",
        ])
        for member in members:
            term = member.terms.first()  # ordering is -started_on
            writer.writerow([
                member.first_name,
                member.last_name,
                member.email,
                member.phone,
                term.tier if term else "",
                term.started_on.isoformat() if term else "",
                term.expires_on.isoformat() if term else "",
                term.price_paid if term else "",
                member.status,
            ])
        return response
```

- [x] **Step 4: Add the Export button**

In `dashboard/templates/dashboard/members.html`, next to the New Member button in the header:

```html
    <a class="actionButton" href="{% url 'dashboard:members_export' %}?q={{ q|urlencode }}&status={{ selected_status|urlencode }}">Export CSV</a>
```

- [x] **Step 5: Wire the URL**

In `dashboard/urls.py`, after the member entries:

```python
    path("members/export.csv", member_views.MemberExportView.as_view(), name="members_export"),
```

- [x] **Step 6: Run the full suite**

Run: `.venv/bin/python manage.py test -v 2`
Expected: PASS, no failures and no errors. Report the exact counts.

- [x] **Step 7: Lint everything this plan touched**

Run: `.venv/bin/python -m flake8 audience dashboard web/constants.py`
Expected: no output.

Actual: `dashboard/` and `web/constants.py` carry pre-existing E501/E402/F401
violations that predate this branch (identical output from `git show
main:dashboard/urls.py | flake8 -`). Every file this plan created or touched —
all of `audience/`, `dashboard/member_views.py`, `dashboard/tests/test_members.py`
— is clean, and the branch adds no new violations.

- [x] **Step 8: Confirm no stray migrations**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: exit 0, "No changes detected".

- [ ] **Step 9: Commit**

```bash
git add dashboard
git commit -m "feat(dashboard): CSV export for the membership roster

One row per member from their latest term, honouring the roster's
filters, so 'export the lapsed members' is filter-then-click.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01J5vdXGkpYi5e5hYvdUDtAW"
```

---

## Deployment

`migrate` and nothing else. No environment variables, no Square configuration, no public-site change. The roster is typed in by hand afterwards.

The local database is stale sqlite, not production — nothing in this plan can be verified against real membership data before deploy.
