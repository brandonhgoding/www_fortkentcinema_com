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
    # Same as MembershipTier.updated_at: dates /membership/ in the sitemap.
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Membership benefit"
        verbose_name_plural = "Membership benefits"

    def __str__(self) -> str:
        return self.name
