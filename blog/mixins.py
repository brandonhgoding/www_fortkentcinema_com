from typing import Any, cast

from django.db import models
from django.utils.text import slugify


class SlugModelMixin(models.Model):
    """
    Mixin to add slug functionality to models.
    Automatically generates a slug from the specified field.
    """

    slug_field = "title"
    # Used when the source text has no ASCII letters or digits at all
    # ("★★★★☆", emoji, Cyrillic), which slugify turns into ''.
    slug_fallback = "item"
    slug = models.SlugField(max_length=100, unique=True, blank=True, null=True)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = self.generate_slug()
        super().save(*args, **kwargs)

    def generate_slug(self, source: str | None = None) -> str:
        """The slug for `source`, or for this instance's `slug_field`.

        Never empty: an empty slug can't be reversed into /blog/<slug>, which
        took down every page that links to the post. The fallback is made
        unique, as Film.generate_slug does, since it carries no meaning of its
        own. A real slug is not: a clash there is reported to the editor.
        """
        if source is None:
            source = getattr(self, self.slug_field)
        # Trimmed to the column: a 200-character subtitle slugifies past the
        # 100-character SlugField, which Postgres rejects outright.
        max_length = self._meta.get_field("slug").max_length
        slug = cast(str, slugify(source))[:max_length].strip("-")
        if slug:
            return slug

        others = type(self)._default_manager.exclude(pk=self.pk)
        slug, n = self.slug_fallback, 2
        while others.filter(slug=slug).exists():
            slug = f"{self.slug_fallback}-{n}"
            n += 1
        return slug
