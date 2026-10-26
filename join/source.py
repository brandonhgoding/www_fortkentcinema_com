"""How the box office ledger learns who bought a website membership.

Registered with ``boxoffice.memberships`` at startup. ``buyer_for`` hands
over the typed name and email for one of our Square orders; ``record``
hears how the sale was entered and moves the order row to match, sending
the welcome email the first time it turns PAID.
"""

import logging

from boxoffice.gateway import OrderData
from boxoffice.memberships import Buyer
from boxoffice.models import MembershipSale
from django.db import transaction

from join.mail import send_welcome
from join.models import MembershipOrder

logger = logging.getLogger(__name__)

KNOWN = (MembershipOrder.Status.PENDING, MembershipOrder.Status.FAILED,
         MembershipOrder.Status.PAID)


class MembershipOrderSource:
    def buyer_for(self, order_id: str) -> Buyer | None:
        order = MembershipOrder.objects.filter(
            square_order_id=order_id, status__in=KNOWN).first()
        if order is None:
            return None
        return Buyer(display_name=order.name, email=order.email, phone="",
                     first_name=order.first_name, last_name=order.last_name)

    def record(self, order_id: str, sale: MembershipSale,
               order: OrderData | None) -> None:
        with transaction.atomic():
            row = (MembershipOrder.objects.select_for_update()
                   .filter(square_order_id=order_id).first())
            if row is None:
                return
            if sale.status == MembershipSale.Status.OK:
                newly_paid = row.status != MembershipOrder.Status.PAID
                row.status = MembershipOrder.Status.PAID
                row.term = sale.term
                row.sale = sale
                row.paid_at = sale.paid_at
                row.error = ""
                if order is not None and not row.square_payment_id:
                    row.square_payment_id = _payment_id(order)
                row.save()
            else:
                if row.status == MembershipOrder.Status.PAID:
                    return  # Late or repeated bad news never undoes a term.
                newly_paid = False
                row.status = MembershipOrder.Status.FAILED
                row.error = sale.error
                row.sale = sale
                row.save()
        if newly_paid:
            try:
                send_welcome(row)
            except Exception:
                logger.exception("Welcome email failed for order %s", row.number)


def _payment_id(order: OrderData) -> str:
    return next((t.payment_id for t in order.tenders if t.paid), "")


SOURCE = MembershipOrderSource()
