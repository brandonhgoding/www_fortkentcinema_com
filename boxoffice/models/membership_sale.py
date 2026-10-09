import datetime
from decimal import Decimal

from django.db import models


class MembershipSale(models.Model):
    """One Square order with a membership line: webhook idempotency and audit."""

    class Status(models.TextChoices):
        OK = "OK", "Entered"
        SKIPPED = "SKIPPED", "Skipped"
        FAILED = "FAILED", "Needs attention"

    order_id = models.CharField(max_length=64, unique=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    tier = models.ForeignKey(
        "audience.MembershipTier",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="square_sales",
    )
    quantity = models.PositiveIntegerField(default=0)
    gross_cents = models.IntegerField(default=0)
    display_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices)
    error = models.TextField(blank=True)
    term = models.OneToOneField(
        "audience.MembershipTerm",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="square_sale",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-closed_at", "-created_at"]

    def __str__(self) -> str:
        return self.order_id

    @property
    def purchase_date(self) -> datetime.date | None:
        if self.closed_at is None:
            return None
        # Imported here: boxoffice.pull imports the models package.
        from boxoffice.pull import business_date

        return business_date(self.closed_at)

    @property
    def gross_dollars(self) -> Decimal:
        return Decimal(self.gross_cents) / 100
