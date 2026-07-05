# cinema/models/film.py
from typing import Any

from django.db import models


class Film(models.Model):
    """
    Film in the system catalog.
    """

    title = models.CharField(max_length=200)
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

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Convert empty string to None for unique constraint
        if self.tmdb_id == "":
            self.tmdb_id = None
        if self.imdb_id == "":
            self.imdb_id = None
        if self.youtube_id == "":
            self.youtube_id = None
        super().save(*args, **kwargs)
