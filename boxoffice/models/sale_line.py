from cinema.models import Engagement, Showtime
from django.db import models

from .square_variation import SquareVariation


class SaleLine(models.Model):
    """The ledger: one row per Square order line item."""

    order_id = models.CharField(max_length=64)
    line_uid = models.CharField(max_length=64)
    # The Eastern day of the sale: when the register closed the order, or when
    # the buyer paid a website order (those stay OPEN in Square, never closed).
    business_date = models.DateField(db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    item_name = models.CharField(max_length=200)
    variation_name = models.CharField(max_length=80, blank=True)
    catalog_object_id = models.CharField(max_length=64, blank=True, db_index=True)
    category_id = models.CharField(max_length=64, blank=True)
    quantity = models.PositiveIntegerField()
    gross_cents = models.IntegerField()
    # What was given back: a refunded ticket stays on its Square order, so
    # the reports count quantity - refunded_quantity and gross - refunded.
    # Today only a website order refunded in full from the dashboard sets
    # these (the whole line); register refunds are not read from Square yet.
    refunded_quantity = models.PositiveIntegerField(default=0)
    refunded_cents = models.IntegerField(default=0)
    variation = models.ForeignKey(
        SquareVariation, null=True, blank=True, on_delete=models.SET_NULL
    )
    engagement = models.ForeignKey(
        Engagement, null=True, blank=True, on_delete=models.SET_NULL
    )
    # The showtime an online ticket order was for; register sales have none.
    # The ticket report dates a line by its show day when this is set.
    showtime = models.ForeignKey(
        Showtime, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order_id", "line_uid"], name="boxoffice_one_row_per_order_line"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_id}/{self.line_uid}"
