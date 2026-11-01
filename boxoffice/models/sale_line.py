from cinema.models import Engagement
from django.db import models

from .square_variation import SquareVariation


class SaleLine(models.Model):
    """The ledger: one row per Square order line item.

    ``business_date`` is the day of the sale, which for a register sale is
    also the day of the show: every report counts by it.
    """

    order_id = models.CharField(max_length=64)
    line_uid = models.CharField(max_length=64)
    # The Eastern day of the sale: when the order was paid, else closed.
    business_date = models.DateField(db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    item_name = models.CharField(max_length=200)
    variation_name = models.CharField(max_length=80, blank=True)
    catalog_object_id = models.CharField(max_length=64, blank=True, db_index=True)
    category_id = models.CharField(max_length=64, blank=True)
    quantity = models.PositiveIntegerField()
    gross_cents = models.IntegerField()
    variation = models.ForeignKey(
        SquareVariation, null=True, blank=True, on_delete=models.SET_NULL
    )
    engagement = models.ForeignKey(
        Engagement, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order_id", "line_uid"], name="boxoffice_one_row_per_order_line"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_id}/{self.line_uid}"
