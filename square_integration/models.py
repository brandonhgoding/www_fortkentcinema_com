# cinema/models.py

from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    """
    Local representation of a Square Catalog Category.

    This is meant to sync 1:1 with a Square 'CATEGORY' object:
      - name -> item_data.name
      - square_id -> Square's catalog object id

    You can attach this to Film/Booking/etc. and,
    when creating/updating Square Items, set:
      item_data["category_id"] = category.square_id
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)

    # Optional: for internal use / admin niceness
    description = models.TextField(blank=True)

    # Square catalog object id for this category (e.g. "ABC123...")
    square_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text="Square Catalog object ID for this category.",
    )

    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-generate slug if not set
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
