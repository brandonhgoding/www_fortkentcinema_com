"""Online ticket facts the dashboard home turns into alerts."""

import datetime
import math

from cinema.models import Showtime
from django.db.models import Count, Q

from tickets.availability import for_showtimes
from tickets.models import TicketOrder

NEARLY_SOLD_OUT_SHARE = 0.9
NEARLY_SOLD_OUT_WINDOW = datetime.timedelta(days=2)


def failures_count() -> int:
    """Orders needing staff attention, whether or not Square took the money."""
    return TicketOrder.objects.filter(status=TicketOrder.Status.FAILED).count()


def nearly_sold_out(now: datetime.datetime) -> list[tuple[Showtime, int, int]]:
    """(showtime, sold, allowance) for showings in the next two days at 90%+.

    Sold is the engagement page's figure: paid plus seats still on hold.
    """
    showtimes = list(
        Showtime.objects.filter(
            is_cancelled=False,
            starts_at__gte=now,
            starts_at__lt=now + NEARLY_SOLD_OUT_WINDOW,
        )
        .select_related("screen")
        .prefetch_related("engagement__engagement_films__film")
        .order_by("starts_at")
    )
    availability = for_showtimes(showtimes, now, square_enabled=False)
    rows = []
    for st in showtimes:
        a = availability[st.pk]
        if a.allowance > 0 and a.sold >= math.ceil(a.allowance * NEARLY_SOLD_OUT_SHARE):
            rows.append((st, a.sold, a.allowance))
    return rows


def cancelled_with_orders() -> list[tuple[Showtime, int]]:
    """(showtime, sold orders) for cancelled showings still holding money.

    Past or future: an unrefunded order is unrefunded either way.
    """
    Status = TicketOrder.Status
    counts_as_sold = Q(status=Status.PAID) | Q(
        status=Status.FAILED, square_payment_id__gt=""
    )
    sold_orders = (
        TicketOrder.objects.filter(counts_as_sold, showtime__is_cancelled=True)
        .values("showtime_id")
        .annotate(n=Count("pk"))
        .values_list("showtime_id", "n")
    )
    counts = dict(sold_orders)
    showtimes = (
        Showtime.objects.filter(pk__in=counts)
        .prefetch_related("engagement__engagement_films__film")
        .order_by("starts_at")
    )
    return [(st, counts[st.pk]) for st in showtimes]
