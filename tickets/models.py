import datetime
import secrets
from decimal import Decimal

from boxoffice.spec import ONLINE_REFERENCE_PREFIX
from django.conf import settings
from django.db import models
from django.db.models import Q

from web.constants import TICKET_HOLD_MINUTES

from tickets.tiers import ONLINE_TIERS

# No 0/O/1/I: the code is read aloud at the door.
NUMBER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_number() -> str:
    return ONLINE_REFERENCE_PREFIX + "".join(
        secrets.choice(NUMBER_ALPHABET) for _ in range(5))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def split_name(name: str) -> tuple[str, str]:
    """A typed full name as (first, last): the first word, then the rest."""
    first, _, last = name.strip().partition(" ")
    return first, last.strip()


class TicketOrder(models.Model):
    """One online checkout attempt for a showtime."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        EXPIRED = "EXPIRED", "Expired"
        REFUNDED = "REFUNDED", "Refunded"
        FAILED = "FAILED", "Needs attention"
        # Square never gave us a payment link, so the buyer never saw a
        # checkout and was told to try again. Terminal; nothing to retry.
        ABANDONED = "ABANDONED", "Never started"

    TIERS = ONLINE_TIERS

    number = models.CharField(max_length=12, unique=True, default=new_number)
    token = models.CharField(max_length=43, unique=True, default=new_token)
    showtime = models.ForeignKey(
        "cinema.Showtime",
        on_delete=models.PROTECT,
        related_name="ticket_orders",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    status = models.CharField(
        max_length=9, choices=Status.choices, default=Status.PENDING
    )
    square_order_id = models.CharField(max_length=64, blank=True, default="")
    square_payment_id = models.CharField(max_length=64, blank=True, default="")
    square_checkout_url = models.URLField(blank=True)
    # The buyer's Square customer profile, found or made at checkout; "" when
    # the directory call failed (the sale still goes ahead).
    square_customer_id = models.CharField(max_length=64, blank=True, default="")
    total_cents = models.PositiveIntegerField()
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["square_order_id"],
                condition=~Q(square_order_id=""),
                name="tickets_one_order_per_square_order",
            )
        ]
        indexes = [
            models.Index(fields=["showtime", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def is_holding(self, now: datetime.datetime) -> bool:
        """PENDING and still inside the hold window: the seats are spoken for."""
        if self.status != self.Status.PENDING:
            return False
        return now < self.created_at + datetime.timedelta(minutes=TICKET_HOLD_MINUTES)

    @property
    def counts_as_sold(self) -> bool:
        """The buyer has a ticket: paid, or paid but the email failed."""
        if self.status == self.Status.PAID:
            return True
        return self.status == self.Status.FAILED and bool(self.square_payment_id)

    @property
    def total_dollars(self) -> Decimal:
        return Decimal(self.total_cents) / 100

    @property
    def breakdown(self) -> str:
        quantities = {line.tier: line.quantity for line in self.lines.all()}
        return ", ".join(
            f"{quantities[tier]} {tier}" for tier in ONLINE_TIERS if tier in quantities
        )


class TicketLine(models.Model):
    order = models.ForeignKey(
        TicketOrder, on_delete=models.CASCADE, related_name="lines"
    )
    tier = models.CharField(max_length=16)
    quantity = models.PositiveIntegerField()
    unit_cents = models.PositiveIntegerField()
    square_variation_id = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "tier"], name="tickets_one_line_per_tier"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="tickets_line_quantity_at_least_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} {self.tier}"
