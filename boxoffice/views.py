import json

from boxoffice import decorators
from boxoffice.gateway import _timestamp
from boxoffice.memberships import order_never_fetched, process_order
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest

from tickets.models import TicketOrder
from tickets.orders import confirm_payment

PAYMENT_EVENTS = {"payment.created", "payment.updated"}


@decorators.square_webhook
def square_webhook(request: HttpRequest) -> HttpResponse:
    """Square's payment events: record the sale once the payment completes.

    Payment-link orders stay OPEN until staff mark the shipment done, often
    days later, so the payment (not the order's completion) is the trigger.
    ``payment.created`` usually arrives APPROVED and ``payment.updated`` brings
    COMPLETED; either is accepted once COMPLETED.

    Square retries anything but a 2xx. process_order records its own failures
    on the sale row, so a well-formed event gets a 200, except a 503 when the
    order was never fetched: Square's retry then fetches it again, and the
    FAILED row stays as the backstop if Square gives up.
    """
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()
    if not isinstance(payload, dict):
        return HttpResponseBadRequest()
    if payload.get("type") not in PAYMENT_EVENTS:
        return HttpResponse()

    try:
        payment = payload["data"]["object"]["payment"]
        status = payment["status"]
        order_id = payment.get("order_id")
        payment_id = payment["id"]
    except (KeyError, TypeError, AttributeError):
        return HttpResponseBadRequest()
    if status == "COMPLETED" and order_id:
        # A ticket order holds no membership, so skip that handler's fetch.
        is_ticket = TicketOrder.objects.filter(square_order_id=order_id).exists()
        sale = None if is_ticket else process_order(order_id)
        # A payment-link ticket order, if this was one; None otherwise.
        confirm_payment(
            order_id, payment_id, paid_at=_timestamp(payment.get("created_at"))
        )
        if sale is not None and order_never_fetched(sale):
            return HttpResponse(status=503)
    return HttpResponse()
