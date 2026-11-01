
from django.core.validators import MinValueValidator
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
        help_text="Short name for the tier in dashboard filters and the member export.",
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
    duration_months = models.PositiveSmallIntegerField(
        default=12, validators=[MinValueValidator(1)]
    )
    free_admissions_per_month = models.PositiveSmallIntegerField(
        default=0,
        help_text="Free admissions this tier includes each calendar month. "
        "0 means none. Resets on the 1st; unused ones do not carry over.",
    )
    featured = models.BooleanField(
        default=False, help_text="Shows the 'Best Value' ribbon."
    )
    is_family_tier = models.BooleanField(
        default=False, help_text="Shows the 'For Families' ribbon."
    )
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
    # Dates /membership/ in the sitemap. Null on rows untouched since the
    # field arrived, rather than claiming they all changed on deploy day.
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ["sort_order", "price"]
        verbose_name = "Membership tier"
        verbose_name_plural = "Membership tiers"
        constraints = [
            # A zero-month tier's default expiry is the day before it starts.
            models.CheckConstraint(
                condition=models.Q(duration_months__gte=1),
                name="audience_membershiptier_duration_at_least_one_month",
            ),
        ]

    def __str__(self) -> str:
        return self.name
