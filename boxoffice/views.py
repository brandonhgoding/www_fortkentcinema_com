import json

from boxoffice import decorators
from boxoffice.memberships import order_never_fetched, process_order
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest


@decorators.square_webhook
def square_webhook(request: HttpRequest) -> HttpResponse:
    """Square's order.updated event: record the sale once the order completes.

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
    if payload.get("type") != "order.updated":
        return HttpResponse()

    try:
        order = payload["data"]["object"]["order_updated"]
        order_id, state = order["order_id"], order["state"]
    except (KeyError, TypeError):
        return HttpResponseBadRequest()
    if state == "COMPLETED":
        sale = process_order(order_id)
        if sale is not None and order_never_fetched(sale):
            return HttpResponse(status=503)
    return HttpResponse()
