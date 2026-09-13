import datetime

from django.db import models
from django.utils import timezone

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
    expires_on = models.DateField(
        help_text="Inclusive: the membership is good through this date."
    )
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

    @property
    def is_current(self) -> bool:
        return self.started_on <= timezone.localdate() <= self.expires_on

    @staticmethod
    def default_expiry(
        started_on: datetime.date, duration_months: int
    ) -> datetime.date:
        return add_months(started_on, duration_months)
