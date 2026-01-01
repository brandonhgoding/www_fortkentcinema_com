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
        return cast(str, slugify(getattr(self, self.slug_field)))
