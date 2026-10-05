from cinema.models import Engagement
from django.db import models


class SquareItem(models.Model):
    """A Square catalog item that Django owns, one live item per engagement."""

    # SET_NULL: deleting a run must not orphan an item in Square.
    engagement = models.ForeignKey(
        Engagement, null=True, on_delete=models.SET_NULL, related_name="square_items"
    )
    square_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    version = models.BigIntegerField(default=0)
    name = models.CharField(max_length=200)
    synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["engagement"],
                condition=models.Q(deleted_at__isnull=True),
                name="boxoffice_one_live_item_per_engagement",
            ),
        ]

    def __str__(self) -> str:
        return self.name
