# cinema/models/engagement_film.py
from typing import ClassVar

from django.db import models
from django.db.models import Manager

from .film import Film


class EngagementFilm(models.Model):
    objects: ClassVar[Manager["EngagementFilm"]]

    engagement = models.ForeignKey(
        "cinema.Engagement",
        on_delete=models.CASCADE,
        related_name="engagement_films",
    )
    film = models.ForeignKey(
        Film, on_delete=models.PROTECT, related_name="engagement_films"
    )
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "position"],
                name="unique_engagement_position",
            ),
            models.UniqueConstraint(
                fields=["engagement", "film"],
                name="unique_engagement_film",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.engagement_id}: {self.film.title} (#{self.position})"
