import json

from boxoffice import decorators
from boxoffice.memberships import process_order
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest


@decorators.square_webhook
def square_webhook(request: HttpRequest) -> HttpResponse:
    """Square's order.updated event: record the sale once the order completes.

    Square retries anything but a 2xx, and process_order records its own
    failures on the sale row, so every well-formed event gets a 200.
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
        process_order(order_id)
    return HttpResponse()
