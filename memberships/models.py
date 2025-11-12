from django.db import models
from django.utils.text import slugify
from square_integration.models import Category


class MembershipBenefit(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MembershipType(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)

    # Sales/fulfillment
    active = models.BooleanField(default=True)
    duration_months = models.PositiveIntegerField(default=12)  # 1, 6, 12, etc.

    # Price
    price_cents = models.PositiveIntegerField(help_text="Price in cents")
    currency = models.CharField(max_length=3, default="USD")

    # Display
    display_order = models.PositiveIntegerField(default=0)

    # Benefits (optional, for web display)
    benefits = models.ManyToManyField(MembershipBenefit, blank=True, related_name="membership_types")

    # Square linkage (filled on first sync)
    square_item_id = models.CharField(max_length=64, blank=True, default="")
    square_item_variation_id = models.CharField(max_length=64, blank=True, default="")
    square_category = models.ForeignKey(to=Category, on_delete=models.RESTRICT, null=True, blank=True)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)
