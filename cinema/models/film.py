# cinema/models/film.py
from typing import Any

from django.db import models
from django.utils.text import slugify


class Film(models.Model):
    """
    Film in the system catalog.
    """

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)
    runtime_minutes = models.PositiveIntegerField(null=True, blank=True)
    rating = models.CharField(max_length=10, blank=True)
    synopsis = models.TextField(blank=True)
    poster_url = models.URLField(blank=True)
    backdrop_url = models.URLField(blank=True)
    overview = models.TextField(blank=True)

    tmdb_id = models.CharField(max_length=50, blank=True, unique=True, null=True)
    imdb_id = models.CharField(max_length=50, blank=True, unique=True, null=True)
    youtube_id = models.CharField(max_length=50, blank=True, unique=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title

    @property
    def description(self) -> str:
        """Prefer our own synopsis; fall back to the TMDB overview."""
        return self.synopsis or self.overview or ""

    @property
    def imdb_url(self) -> str:
        return f"https://www.imdb.com/title/{self.imdb_id}/" if self.imdb_id else ""

    def generate_slug(self) -> str:
        """Films have no release year, so remakes collide (two `The Mummy`s).
        Suffix rather than raise."""
        base = slugify(self.title) or "film"
        slug = base
        n = 2
        while (
            Film.objects.filter(slug=slug).exclude(pk=self.pk).exists()
        ):
            slug = f"{base}-{n}"
            n += 1
        return slug

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Convert empty string to None for unique constraint
        if self.tmdb_id == "":
            self.tmdb_id = None
        if self.imdb_id == "":
            self.imdb_id = None
        if self.youtube_id == "":
            self.youtube_id = None
        if not self.slug:
            self.slug = self.generate_slug()
        super().save(*args, **kwargs)
