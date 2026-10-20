import datetime
from zoneinfo import ZoneInfo

from boxoffice.models import SquareItem, SquareVariation
from boxoffice.spec import SQUARE_TIERS
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.utils import timezone
from web.constants import TICKET_PRICES

from tickets.models import TicketLine, TicketOrder, split_name

UNIT_CENTS = {"adult": 800, "senior": 700, "child": 600}


def make_showtime(**over) -> Showtime:
    """A confirmed showing of "Dune" at 19:00 Eastern, seven days from today."""
    today = timezone.localdate()
    screen = Screen.objects.create(name="Screen 1", capacity=100)
    film = Film.objects.create(title="Dune", runtime_minutes=155)
    engagement = Engagement.objects.create(
        screen=screen,
        start_date=today,
        end_date=today + datetime.timedelta(days=14),
        status="CONFIRMED",
    )
    EngagementFilm.objects.create(engagement=engagement, film=film, position=1)
    starts_at = over.pop("starts_at", None)
    if starts_at is None:
        day = today + datetime.timedelta(days=7)
        starts_at = datetime.datetime.combine(
            day, datetime.time(19, 0), tzinfo=ZoneInfo("America/New_York")
        )
    return Showtime.objects.create(
        engagement=engagement, screen=screen, starts_at=starts_at, **over
    )


def make_order(
    showtime: Showtime, *, status: str = "PENDING", lines: dict | None = None, **over
) -> TicketOrder:
    lines = {"adult": 1} if lines is None else lines
    # Callers may give a full `name`; it is split like the migration does.
    first, last = split_name(over.pop("name", "Ann Lee"))
    fields = {
        "first_name": first,
        "last_name": last,
        "email": "ann@example.com",
        "phone": "207-555-0100",
        "total_cents": sum(UNIT_CENTS[t] * q for t, q in lines.items()),
    }
    fields.update(over)
    order = TicketOrder.objects.create(showtime=showtime, status=status, **fields)
    for tier, quantity in lines.items():
        TicketLine.objects.create(
            order=order,
            tier=tier,
            quantity=quantity,
            unit_cents=UNIT_CENTS[tier],
            square_variation_id=f"VAR-{tier}",
        )
    return order


def make_live_item(engagement: Engagement, *, prefix: str = "") -> SquareItem:
    """A pushed Square item for the run, with one variation per tier.

    Square IDs are unique: give each further live item in a test a `prefix`.
    """
    item = SquareItem.objects.create(
        engagement=engagement, square_id=f"{prefix}item-1", name=engagement.title
    )
    for ordinal, tier in enumerate(SQUARE_TIERS):
        SquareVariation.objects.create(
            item=item,
            square_id=f"{prefix}var-{tier}",
            sku=f"fkc-eng-{engagement.pk}-{tier}",
            tier=tier,
            name=tier.title(),
            price_cents=TICKET_PRICES[tier] * 100,
            ordinal=ordinal,
        )
    return item


def age(order: TicketOrder, minutes: int) -> None:
    """Rewind the order's created_at by `minutes` (auto_now_add blocks save())."""
    TicketOrder.objects.filter(pk=order.pk).update(
        created_at=order.created_at - datetime.timedelta(minutes=minutes)
    )
