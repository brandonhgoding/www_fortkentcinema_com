"""How many online tickets a showtime has left, and whether it can sell now."""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass

from boxoffice.models import SquareItem
from boxoffice.sync import live_item
from cinema.models import Engagement, EngagementStatus, Showtime
from django.db.models import Q, Sum

from tickets.models import TicketLine, TicketOrder
from web.constants import TICKET_CUTOFF_MINUTES, TICKET_HOLD_MINUTES


@dataclass(frozen=True)
class Availability:
    purchasable: bool
    reason: str
    sold: int
    remaining: int
    allowance: int


def _taken_lines(now: datetime.datetime):
    """Lines whose seats are gone: sold (see counts_as_sold) or still held."""
    Status = TicketOrder.Status
    hold_start = now - datetime.timedelta(minutes=TICKET_HOLD_MINUTES)
    return TicketLine.objects.filter(
        Q(order__status=Status.PAID)
        | Q(order__status=Status.FAILED, order__square_payment_id__gt="")
        | Q(order__status=Status.PENDING, order__created_at__gt=hold_start)
    )


def sold(showtime: Showtime, now: datetime.datetime) -> int:
    total = (
        _taken_lines(now)
        .filter(order__showtime=showtime)
        .aggregate(total=Sum("quantity"))["total"]
    )
    return total or 0


def remaining(showtime: Showtime, now: datetime.datetime) -> int:
    return max(showtime.effective_online_allowance - sold(showtime, now), 0)


def _has_item(item: SquareItem | None) -> bool:
    return item is not None and bool(item.square_id)


def _decide(
    showtime: Showtime,
    now: datetime.datetime,
    *,
    square_enabled: bool,
    sold_count: int,
    has_item: bool,
) -> Availability:
    allowance = showtime.effective_online_allowance
    left = max(allowance - sold_count, 0)
    engagement = showtime.engagement
    cutoff = showtime.starts_at - datetime.timedelta(minutes=TICKET_CUTOFF_MINUTES)
    if not square_enabled:
        reason = "disabled"
    elif (
        engagement.status != EngagementStatus.CONFIRMED
        or not engagement.show_in_main_listings
    ):
        reason = "not_listed"
    elif showtime.is_cancelled:
        reason = "cancelled"
    elif now >= cutoff:
        reason = "cutoff"
    elif not has_item:
        reason = "no_item"
    elif left == 0:
        reason = "sold_out"
    else:
        reason = ""
    return Availability(
        purchasable=reason == "",
        reason=reason,
        sold=sold_count,
        remaining=left,
        allowance=allowance,
    )


def check(
    showtime: Showtime, now: datetime.datetime, *, square_enabled: bool
) -> Availability:
    return _decide(
        showtime,
        now,
        square_enabled=square_enabled,
        sold_count=sold(showtime, now),
        has_item=_has_item(live_item(showtime.engagement)),
    )


def for_showtimes(
    showtimes: Iterable[Showtime], now: datetime.datetime, *, square_enabled: bool
) -> dict[int, Availability]:
    """check() for many showtimes in two queries; keyed by showtime pk."""
    showtimes = list(showtimes)
    if not showtimes:
        return {}
    sold_by_showtime = dict(
        _taken_lines(now)
        .filter(order__showtime__in=[s.pk for s in showtimes])
        .values("order__showtime_id")
        .annotate(total=Sum("quantity"))
        .values_list("order__showtime_id", "total")
    )
    engagements_with_items = set(
        SquareItem.objects.filter(
            engagement_id__in={s.engagement_id for s in showtimes},
            deleted_at__isnull=True,
            square_id__gt="",
        ).values_list("engagement_id", flat=True)
    )
    return {
        s.pk: _decide(
            s,
            now,
            square_enabled=square_enabled,
            sold_count=sold_by_showtime.get(s.pk, 0),
            has_item=s.engagement_id in engagements_with_items,
        )
        for s in showtimes
    }


def variation_ids(engagement: Engagement) -> dict[str, str]:
    """Tier -> Square variation id on the run's live item; empty without one."""
    item = live_item(engagement)
    if item is None:
        return {}
    return dict(item.variations.values_list("tier", "square_id"))
