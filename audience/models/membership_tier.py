from typing import Any, ClassVar

from django.core.exceptions import ValidationError
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
    checkout_url = models.URLField(blank=True, help_text="The Square payment link.")
    square_variation_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="The ID of this tier's 'Annual' variation in Square "
        "(Items → the item → the variation's ID in the URL). Sales of that "
        "variation create terms for this tier.",
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
            models.UniqueConstraint(
                fields=["square_variation_id"],
                condition=~models.Q(square_variation_id=""),
                name="audience_membershiptier_square_variation_id_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    SLUG_IS_FIXED: ClassVar[str] = (
        "A tier's slug is fixed once saved: Square redirects and GA4 "
        "tracking carry it."
    )

    def _slug_changed(self) -> bool:
        """Whether this saved tier's slug differs from the stored one.

        Asks the database rather than remembering the loaded value, so a
        deliberate QuerySet.update() — the escape hatch for a real rename —
        followed by refresh_from_db() is not mistaken for an edit.
        """
        if self._state.adding or self.pk is None:
            return False
        stored = (
            type(self)
            ._base_manager.filter(pk=self.pk)
            .values_list("slug", flat=True)
            .first()
        )
        return stored is not None and stored != self.slug

    def clean(self) -> None:
        if self._slug_changed():
            raise ValidationError({"slug": self.SLUG_IS_FIXED})
        # A listed tier's card is a Join button pointing at checkout_url;
        # without one it renders href="" and goes nowhere.
        if self.show_on_membership_page and not self.checkout_url:
            raise ValidationError(
                {
                    "checkout_url": "A tier listed on the membership page "
                    "needs its Square payment link."
                }
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        # The forms and admin already lock the field; this catches code.
        update_fields = kwargs.get("update_fields")
        if (update_fields is None or "slug" in update_fields) and (
            self._slug_changed()
        ):
            raise ValueError(self.SLUG_IS_FIXED)
        super().save(*args, **kwargs)
