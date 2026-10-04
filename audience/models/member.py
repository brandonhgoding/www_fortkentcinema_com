import datetime
from collections.abc import Collection
from typing import ClassVar

from django.db import models
from django.utils import timezone

from audience.dates import month_bounds

# How close to expiry a membership counts as "Expiring soon": the roster's
# amber pill and the term ledger's Expiring window both read this, so the
# two screens agree about which memberships are nearly up. Affects what
# staff see and nothing else — no mail is sent.
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

    @property
    def current_term(self):
        """The term covering today, or None.

        Iterates the related manager rather than filtering in SQL so that a
        list view's prefetch_related("terms__tier") answers every row from
        one query per relation (including the tier FK templates dereference).
        Terms are ordered newest-first, so a renewal wins over the term it
        overlaps.
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
    def covered_through(self) -> datetime.date | None:
        """The last day of unbroken cover from today, or None if not covered.

        Follows back-to-back and overlapping terms forward from the one
        covering today, so an early renewal pushes the date out rather than
        leaving the member "expiring" on the term it renews. A single day
        without cover ends the chain. Walks the prefetched terms, like
        `current_term`.
        """
        today = timezone.localdate()
        covered: datetime.date | None = None
        for term in sorted(self.terms.all(), key=lambda t: t.started_on):
            if term.expires_on < today:
                continue
            if covered == datetime.date.max:
                break  # Nothing can extend it, and the day after overflows.
            reaches = today if covered is None else covered + datetime.timedelta(days=1)
            if term.started_on > reaches:
                break
            covered = max(covered or term.expires_on, term.expires_on)
        return covered

    @property
    def status(self) -> str:
        """One of "active", "expiring", "upcoming", "lapsed" — drives the
        roster pill.

        "expiring" is judged on `covered_through`, not the current term's
        own expiry. "upcoming" is a member with no cover today but a term
        still to start — booked ahead, not lapsed.
        """
        covered = self.covered_through
        if covered is None:
            today = timezone.localdate()
            if any(term.started_on > today for term in self.terms.all()):
                return "upcoming"
            return "lapsed"
        days_left = (covered - timezone.localdate()).days
        if days_left <= EXPIRING_SOON_DAYS:
            return "expiring"
        return "active"

    STATUS_LABELS: ClassVar[dict[str, str]] = {
        "active": "Active",
        "expiring": "Expiring soon",
        # Same words as the term ledger's "future" window.
        "upcoming": "Not started yet",
        "lapsed": "Lapsed",
    }

    @property
    def status_label(self) -> str:
        return self.STATUS_LABELS[self.status]

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

        Iterates the related manager rather than filtering in SQL for the
        same reason `current_term` does: it lets a caller that has done
        prefetch_related("free_admissions") answer every month for a
        member from one query, instead of one query per month.
        """
        first, last = month_bounds(year, month)
        return sum(
            1
            for admission in self.free_admissions.all()
            if first <= admission.redeemed_on <= last
        )

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        # Normalise before validation, not just in save(): every ModelForm
        # (the admin's included) runs validate_unique first, and an exact-
        # case lookup would let "ADA@" past a stored "ada@" into the index.
        self.email = (self.email or "").strip().lower()
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs) -> None:
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)
