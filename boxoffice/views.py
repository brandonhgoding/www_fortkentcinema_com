import json
import logging

from boxoffice import decorators
from boxoffice.gateway import parse_timestamp
from boxoffice.memberships import order_never_fetched, process_order
from boxoffice.payment_events import dispatch, dispatch_dispute, dispatch_refund
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest

logger = logging.getLogger(__name__)

PAYMENT_EVENTS = {"payment.created", "payment.updated"}
# A refund made from the Square dashboard or POS rather than the site's
# Refund button. ``refund.created`` is usually PENDING and ``refund.updated``
# brings COMPLETED; either is accepted once COMPLETED, like payments.
REFUND_EVENTS = {"refund.created", "refund.updated"}
# A chargeback. Every state change comes through ``dispute.state.updated``;
# ``dispute.created`` is the first one.
DISPUTE_EVENTS = {"dispute.created", "dispute.state.updated"}


def _amount_cents(payment: dict) -> int | None:
    """What the buyer paid (or got back), or None when the event does not say."""
    money = payment.get("amount_money")
    amount = money.get("amount") if isinstance(money, dict) else None
    return amount if isinstance(amount, int) and not isinstance(amount, bool) else None


@decorators.square_webhook
def square_webhook(request: HttpRequest) -> HttpResponse:
    """Square's payment events: record the sale once the payment completes.

    Payment-link orders stay OPEN until staff mark the shipment done, often
    days later, so the payment (not the order's completion) is the trigger.
    ``payment.created`` usually arrives APPROVED and ``payment.updated`` brings
    COMPLETED; either is accepted once COMPLETED.

    Registered handlers (the tickets app's) get the payment first; the
    membership handler runs only when none claims it. Square retries anything
    but a 2xx. process_order records its own failures on the sale row, so a
    well-formed event gets a 200, except a 503 when a retry could help: the
    order was never fetched, or a handler crashed. The FAILED row stays as
    the backstop if Square gives up.
    """
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()
    if not isinstance(payload, dict):
        return HttpResponseBadRequest()
    kind = payload.get("type")
    if kind in REFUND_EVENTS:
        return _refund(payload)
    if kind in DISPUTE_EVENTS:
        return _dispute(payload)
    if kind not in PAYMENT_EVENTS:
        return HttpResponse()

    try:
        payment = payload["data"]["object"]["payment"]
        status = payment["status"]
        order_id = payment.get("order_id")
        payment_id = payment["id"]
    except (KeyError, TypeError, AttributeError):
        return HttpResponseBadRequest()
    if status == "COMPLETED" and order_id:
        paid_at = parse_timestamp(payment.get("created_at"))
        result = dispatch(order_id, payment_id, paid_at, _amount_cents(payment))
        retry = result.failed
        if not result.claimed:
            try:
                sale = process_order(order_id)
            except Exception:
                logger.exception("Membership handler failed for order %s", order_id)
                retry = True
            else:
                retry = retry or (sale is not None and order_never_fetched(sale))
        if retry:
            return HttpResponse(status=503)
    return HttpResponse()


def _refund(payload: dict) -> HttpResponse:
    """A refund that completed outside the site: tell whoever sold the thing.

    Nothing here touches memberships (a refunded membership is staff's call),
    so an unclaimed refund is simply acknowledged.
    """
    try:
        refund = payload["data"]["object"]["refund"]
        refund_id = refund["id"]
        payment_id = refund["payment_id"]
        status = refund["status"]
    except (KeyError, TypeError, AttributeError):
        return HttpResponseBadRequest()
    if status != "COMPLETED":
        return HttpResponse()
    refunded_at = parse_timestamp(refund.get("updated_at") or refund.get("created_at"))
    result = dispatch_refund(payment_id, refund_id, refunded_at,
                             _amount_cents(refund))
    return HttpResponse(status=503 if result.failed else 200)


def _dispute(payload: dict) -> HttpResponse:
    """A chargeback, new or in a new state: tell whoever sold the thing."""
    try:
        dispute = payload["data"]["object"]["dispute"]
        dispute_id = dispute["id"]
        payment_id = dispute["disputed_payment"]["payment_id"]
        state = dispute["state"]
    except (KeyError, TypeError, AttributeError):
        return HttpResponseBadRequest()
    reason = dispute.get("reason") or ""
    result = dispatch_dispute(payment_id, dispute_id, state, reason)
    return HttpResponse(status=503 if result.failed else 200)
