"""What the box office ledger may ask the website about its orders."""
import datetime
from collections.abc import Iterable

from tickets.models import TicketOrder


class TicketOrders:
    """``boxoffice.pull.WebsiteOrders`` backed by TicketOrder."""

    def refunded(self, order_ids: Iterable[str]) -> set[str]:
        return set(TicketOrder.objects.filter(
            square_order_id__in=set(order_ids), status=TicketOrder.Status.REFUNDED,
        ).values_list("square_order_id", flat=True))

    def paid(self, start: datetime.datetime, end: datetime.datetime) -> set[str]:
        return set(TicketOrder.objects.filter(paid_at__gte=start, paid_at__lt=end)
                   .exclude(square_order_id="")
                   .values_list("square_order_id", flat=True))
