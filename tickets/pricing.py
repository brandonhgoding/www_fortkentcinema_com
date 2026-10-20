"""Ticket prices for a showtime, matinee-aware. Amounts are in cents."""

from dataclasses import dataclass
from datetime import datetime

from boxoffice.spec import SQUARE_TIERS
from web.constants import TICKET_PRICES
from web.services.cinema_data import CINEMA_TZ


@dataclass(frozen=True)
class PriceRow:
    tier: str
    label: str
    unit_cents: int
    discount_cents: int


def is_matinee(starts_at: datetime) -> bool:
    """True when the show starts at or before the matinee cut-off, Eastern time."""
    return starts_at.astimezone(CINEMA_TZ).time() <= TICKET_PRICES["matinee_until"]


def unit_cents(tier: str, starts_at: datetime) -> int:
    price = TICKET_PRICES[tier]
    if is_matinee(starts_at):
        price = min(price, TICKET_PRICES["matinee"])
    return price * 100


def discount_cents(tier: str, starts_at: datetime) -> int:
    """How much the matinee price saves against the list price (never negative)."""
    if not is_matinee(starts_at):
        return 0
    return max(TICKET_PRICES[tier] * 100 - unit_cents(tier, starts_at), 0)


def price_table(starts_at: datetime) -> list[PriceRow]:
    return [
        PriceRow(
            tier,
            tier.capitalize(),
            unit_cents(tier, starts_at),
            discount_cents(tier, starts_at),
        )
        for tier in SQUARE_TIERS
    ]
