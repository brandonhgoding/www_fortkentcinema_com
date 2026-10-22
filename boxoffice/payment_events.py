"""Who gets told about a completed Square payment.

Other apps register a handler at startup (``tickets.apps``); the webhook
offers each handler the payment in registration order and stops at the
first that claims it. ``boxoffice`` itself never imports those apps.
Membership sales are handled by the webhook after no handler claims the
payment, so a ticket order never pays for a membership fetch.

Refunds and disputes (chargebacks) made outside the site are offered the
same way, keyed by the payment they reverse, so a ticket refunded from the
Square dashboard or contested at the buyer's bank does not stay redeemable.
"""
import dataclasses
import datetime
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# (square_order_id, payment_id, paid_at, amount_cents) -> True when the order
# was the handler's own and is now dealt with (a repeat is dealt with too).
# amount_cents is None when the event did not say what was paid.
PaymentHandler = Callable[[str, str, datetime.datetime | None, int | None], bool]

# (payment_id, refund_id, refunded_at, amount_cents) -> True when the refunded
# payment was the handler's own. amount_cents is None when the event did not
# say how much went back.
RefundHandler = Callable[[str, str, datetime.datetime | None, int | None], bool]

# (payment_id, dispute_id, state, reason) -> True when the disputed payment
# was the handler's own. state is Square's (EVIDENCE_REQUIRED, WON, LOST, ...).
DisputeHandler = Callable[[str, str, str, str], bool]

_handlers: list[PaymentHandler] = []
_refund_handlers: list[RefundHandler] = []
_dispute_handlers: list[DisputeHandler] = []


def register_payment_handler(handler: PaymentHandler) -> None:
    if handler not in _handlers:
        _handlers.append(handler)


def register_refund_handler(handler: RefundHandler) -> None:
    if handler not in _refund_handlers:
        _refund_handlers.append(handler)


def register_dispute_handler(handler: DisputeHandler) -> None:
    if handler not in _dispute_handlers:
        _dispute_handlers.append(handler)


@dataclasses.dataclass(frozen=True)
class Dispatch:
    claimed: bool
    failed: bool  # a handler raised: the event is worth a retry from Square


def dispatch(order_id: str, payment_id: str, paid_at: datetime.datetime | None,
             amount_cents: int | None) -> Dispatch:
    """Offer the payment to each handler; one handler's crash costs no other."""
    return _offer(_handlers, "Payment", order_id, order_id, payment_id, paid_at,
                  amount_cents)


def dispatch_refund(payment_id: str, refund_id: str,
                    refunded_at: datetime.datetime | None,
                    amount_cents: int | None) -> Dispatch:
    """Offer a completed refund to each refund handler."""
    return _offer(_refund_handlers, "Refund", payment_id, payment_id, refund_id,
                  refunded_at, amount_cents)


def dispatch_dispute(payment_id: str, dispute_id: str, state: str,
                     reason: str) -> Dispatch:
    """Offer a dispute (new, or with a new state) to each dispute handler."""
    return _offer(_dispute_handlers, "Dispute", payment_id, payment_id,
                  dispute_id, state, reason)


def _offer(handlers: list, kind: str, subject: str, *args) -> Dispatch:
    failed = False
    for handler in list(handlers):
        try:
            if handler(*args):
                return Dispatch(claimed=True, failed=failed)
        except Exception:
            logger.exception("%s handler %s failed for %s", kind,
                             getattr(handler, "__name__", handler), subject)
            failed = True
    return Dispatch(claimed=False, failed=failed)
