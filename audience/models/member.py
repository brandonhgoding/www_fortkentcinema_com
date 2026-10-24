import datetime
from collections.abc import Callable, Collection
from typing import ClassVar, TypeVar, cast

from django.db import models
from django.utils import timezone

from audience.dates import month_bounds

from .membership_term import MembershipTerm

# How close to expiry a membership counts as "Expiring soon": the roster's
# amber pill and the term ledger's Expiring window both read this, so the
# two screens agree about which memberships are nearly up. Affects what
# staff see and nothing else — no mail is sent.
EXPIRING_SOON_DAYS = 30

T = TypeVar("T")


class MemberStatus(models.TextChoices):
    """A member's standing today, derived from their terms, never stored.

    The one place these words live: the roster pill, its filter dropdown
    and the term ledger's matching windows all read them from here.
    """

    ACTIVE = "active", "Active"
    EXPIRING = "expiring", "Expiring soon"
    UPCOMING = "upcoming", "Not started yet"
    LAPSED = "lapsed", "Lapsed"


class MemberManager(models.Manager):
    def active(self, on: datetime.date | None = None) -> models.QuerySet["Member"]:
        """Members whose terms cover `on` (today by default)."""
        on = on or timezone.localdate()
        return self.filter(MembershipTerm.covering(on, via="terms__")).distinct()


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

    def reload_terms(self) -> list[MembershipTerm]:
        """Read this member's terms, with their tiers, from the database.

        Replaces any terms prefetched before a write, and keeps the fresh
        read as the prefetch, so the properties below answer from the same
        rows as the caller instead of querying again.
        """
        getattr(self, "_prefetched_objects_cache", {}).pop("terms", None)
        models.prefetch_related_objects(
            [self],
            models.Prefetch(
                "terms", queryset=MembershipTerm.objects.select_related("tier")
            ),
        )
        return list(self.terms.all())

    def _from_terms(self, name: str, compute: Callable[[datetime.date], T]) -> T:
        """`compute(today)`, worked out once per set of prefetched terms.

        A roster row reads current_term and covered_through a dozen times
        between the pill, the tier column and the allowance; walking the
        terms every time was a quarter of the page's render. The answer is
        kept only while it can still be right: for the same prefetched
        result (reload_terms() or refresh_from_db() replaces it) and the
        same date. Without a prefetch every read queries anyway, so nothing
        is kept and a term added since is always seen.
        """
        today = timezone.localdate()
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("terms")
        if prefetched is None:
            return compute(today)
        memo = self.__dict__.setdefault("_terms_memo", {})
        hit = memo.get(name)
        # `is`, not id(): the memo holds the old result alive, so a fresh
        # prefetch can never be mistaken for it.
        if hit is not None and hit[0] is prefetched and hit[1] == today:
            return cast(T, hit[2])
        value = compute(today)
        memo[name] = (prefetched, today, value)
        return value

    @property
    def current_term(self) -> MembershipTerm | None:
        """The term covering today, or None.

        Iterates the related manager rather than filtering in SQL so that a
        list view's prefetch_related("terms__tier") answers every row from
        one query per relation (including the tier FK templates dereference).
        Terms are ordered newest-first, so a renewal wins over the term it
        overlaps.
        """

        def compute(today: datetime.date) -> MembershipTerm | None:
            return next((t for t in self.terms.all() if t.covers(today)), None)

        return self._from_terms("current_term", compute)

    @property
    def is_active(self) -> bool:
        return self.current_term is not None

    @property
    def covered_through(self) -> datetime.date | None:
        """The last day of unbroken cover from today, or None if not covered.

        Follows back-to-back and overlapping terms forward from the one
        covering today, so an early renewal pushes the date out rather than
        leaving the member "expiring" on the term it renews. A single day
        without cover ends the chain. Walks the prefetched terms, and is
        kept between reads, like `current_term`.
        """
        return self._from_terms("covered_through", self._covered_through)

    def _covered_through(self, today: datetime.date) -> datetime.date | None:
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
    def status(self) -> "MemberStatus":
        """Drives the roster pill and its filter.

        EXPIRING is judged on `covered_through`, not the current term's
        own expiry. UPCOMING is a member with no cover today but a term
        still to start — booked ahead, not lapsed.
        """
        covered = self.covered_through
        if covered is None:
            today = timezone.localdate()
            if any(term.started_on > today for term in self.terms.all()):
                return MemberStatus.UPCOMING
            return MemberStatus.LAPSED
        days_left = (covered - timezone.localdate()).days
        if days_left <= EXPIRING_SOON_DAYS:
            return MemberStatus.EXPIRING
        return MemberStatus.ACTIVE

    @property
    def status_label(self) -> str:
        return self.status.label

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
