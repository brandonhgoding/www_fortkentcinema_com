from typing import Any, ClassVar

from django.db import models
from django.db.models import Manager

from .engagement import Engagement
from .screen import Screen


class Showtime(models.Model):
    objects: ClassVar[Manager["Showtime"]]

    class CaptionChoices(models.TextChoices):
        cc = "CC", "Closed Captions"
        oc = "OC", "Open Captions"

    # Type hints for ForeignKey _id attributes (set by Django at runtime)
    engagement_id: int | None
    screen_id: int | None

    engagement = models.ForeignKey(
        Engagement, on_delete=models.CASCADE, related_name="showtimes"
    )
    # screen = actual screen for this specific performance
    screen = models.ForeignKey(
        Screen, on_delete=models.PROTECT, related_name="showtimes"
    )

    starts_at = models.DateTimeField()

    is_cancelled = models.BooleanField(default=False)
    captions = models.CharField(
        null=True,
        blank=True,
        default=None,
        max_length=2,
        choices=CaptionChoices.choices,
    )

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["engagement", "starts_at"]),
            models.Index(fields=["screen", "is_cancelled", "starts_at"]),
        ]
        constraints = [
            # Cancelled showtimes are kept as history and must not hold the
            # slot, or re-booking it fails here after the overlap check
            # (which skips them) has already passed it.
            models.UniqueConstraint(
                fields=["screen", "starts_at"],
                condition=models.Q(is_cancelled=False),
                name="unique_screen_starts_at",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.engagement.display_title} @ {self.starts_at}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.engagement_id:
            if not self.screen_id:
                self.screen_id = self.engagement.screen_id
        super().save(*args, **kwargs)
