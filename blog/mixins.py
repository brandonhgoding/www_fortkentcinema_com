from typing import Any, cast

from django.db import models
from django.utils.text import slugify


class SlugModelMixin(models.Model):
    """
    Mixin to add slug functionality to models.
    Automatically generates a slug from the specified field.
    """

    slug_field = "title"
    slug = models.SlugField(max_length=100, unique=True, blank=True, null=True)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = self.generate_slug()
        super().save(*args, **kwargs)

    def generate_slug(self) -> str:
        # Trimmed to the column: a 200-character subtitle slugifies past the
        # 100-character SlugField, which Postgres rejects outright.
        max_length = self._meta.get_field("slug").max_length
        return cast(str, slugify(getattr(self, self.slug_field)))[:max_length].strip("-")
