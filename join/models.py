"""A membership bought on the site: one row per checkout attempt.

The row holds what the buyer typed and where the Square checkout stands.
The member and term themselves are entered by ``boxoffice.memberships``
when Square reports the payment; this row then points at them.
"""

import secrets
from decimal import Decimal

from django.db import models
from django.db.models import Q

NUMBER_PREFIX = "FKM-"
# No 0/O/1/I: the code is read aloud at the box office.
NUMBER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_number() -> str:
    return NUMBER_PREFIX + "".join(
        secrets.choice(NUMBER_ALPHABET) for _ in range(5))


def new_token() -> str:
    return secrets.token_urlsafe(32)


class MembershipOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        # Paid, but the term could not be entered: staff retry it from the
        # Square sales list.
        FAILED = "FAILED", "Needs attention"
        # Square never gave us a payment link, so the buyer never saw a
        # checkout and was told to try again. Terminal; nothing to retry.
        ABANDONED = "ABANDONED", "Never started"

    number = models.CharField(max_length=12, unique=True, default=new_number)
    token = models.CharField(max_length=43, unique=True, default=new_token)
    tier = models.ForeignKey(
        "audience.MembershipTier", on_delete=models.PROTECT, related_name="orders"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    status = models.CharField(
        max_length=9, choices=Status.choices, default=Status.PENDING
    )
    square_order_id = models.CharField(max_length=64, blank=True, default="")
    square_payment_id = models.CharField(max_length=64, blank=True, default="")
    square_checkout_url = models.URLField(blank=True)
    square_customer_id = models.CharField(max_length=64, blank=True, default="")
    total_cents = models.PositiveIntegerField()
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    term = models.ForeignKey(
        "audience.MembershipTerm", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="orders",
    )
    sale = models.ForeignKey(
        "boxoffice.MembershipSale", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="orders",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["square_order_id"],
                condition=~Q(square_order_id=""),
                name="join_one_order_per_square_order",
            )
        ]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def total_dollars(self) -> Decimal:
        return Decimal(self.total_cents) / 100
