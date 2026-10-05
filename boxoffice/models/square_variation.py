from django.db import models

from .square_item import SquareItem


class SquareVariation(models.Model):
    item = models.ForeignKey(
        SquareItem, on_delete=models.CASCADE, related_name="variations"
    )
    square_id = models.CharField(max_length=64, unique=True)
    sku = models.CharField(max_length=64, unique=True)
    tier = models.CharField(max_length=16)
    name = models.CharField(max_length=80)
    price_cents = models.PositiveIntegerField()
    ordinal = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "tier"], name="boxoffice_one_variation_per_tier"
            ),
        ]

    def __str__(self) -> str:
        return self.sku
