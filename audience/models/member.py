import datetime
from typing import ClassVar

from django.db import models
from django.utils import timezone

from audience.dates import month_bounds

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

    def save(self, *args, **kwargs) -> None:
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)
