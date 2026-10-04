import datetime

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
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

    tier = models.ForeignKey(
        "audience.MembershipTier",
        related_name="terms",
        on_delete=models.PROTECT,
        help_text="Retire a tier with show_on_membership_page instead of "
        "deleting it — terms are revenue records.",
    )
    started_on = models.DateField()
    expires_on = models.DateField(
        help_text="Inclusive: the membership is good through this date."
    )
    price_paid = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="What actually changed hands, so a comped or discounted "
        "membership stays truthful and past revenue survives a price change.",
    )
    purchased_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # -id breaks ties between same-day starts, so "newest first" is
        # the later entry rather than whatever order the database returns.
        ordering = ["-started_on", "-id"]
        verbose_name = "Membership term"
        verbose_name_plural = "Membership terms"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_on__gte=models.F("started_on")),
                name="audience_membershipterm_expires_on_or_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(price_paid__gte=0),
                name="audience_membershipterm_price_paid_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tier}: {self.started_on} – {self.expires_on}"

    def clean(self) -> None:
        if self.started_on and self.expires_on and self.expires_on < self.started_on:
            raise ValidationError(
                {"expires_on": "Expiry cannot be before the start date."}
            )

    def covers(self, on: datetime.date) -> bool:
        """Whether this term covers `on`. Both ends are inclusive.

        The Python half of the one definition; `covering` is the SQL half.
        """
        return self.started_on <= on <= self.expires_on

    @staticmethod
    def covering(on: datetime.date, via: str = "") -> models.Q:
        """A filter for terms covering `on`, matching `covers`.

        `via` spans a relation in one filter() call, e.g. via="terms__" on
        Member, so both bounds apply to the same term.
        """
        return models.Q(
            **{f"{via}started_on__lte": on, f"{via}expires_on__gte": on}
        )

    @property
    def is_current(self) -> bool:
        return self.covers(timezone.localdate())

    @staticmethod
    def default_expiry(
        started_on: datetime.date, duration_months: int
    ) -> datetime.date:
        """The last covered day of a term of `duration_months`.

        `expires_on` is inclusive, so a year from 1 March runs through the
        last day of February, and its renewal starts on the anniversary
        without overlapping it.

        Raises OverflowError when that day is past date.max. A term whose
        anniversary would be 1 January 10000 still gets date.max, the eve
        of a day that cannot be represented.
        """
        try:
            anniversary = add_months(started_on, duration_months)
        except OverflowError:
            months_to_new_year_10000 = (
                datetime.MAXYEAR + 1 - started_on.year
            ) * 12 - (started_on.month - 1)
            if started_on.day == 1 and duration_months == months_to_new_year_10000:
                return datetime.date.max
            raise
        return anniversary - datetime.timedelta(days=1)
