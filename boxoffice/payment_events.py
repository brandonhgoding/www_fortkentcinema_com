"""Who gets told about a completed Square payment.

Other apps register a handler at startup (``tickets.apps``); the webhook
offers each handler the payment in registration order and stops at the
first that claims it. ``boxoffice`` itself never imports those apps.
Membership sales are handled by the webhook after no handler claims the
payment, so a ticket order never pays for a membership fetch.
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

_handlers: list[PaymentHandler] = []


def register_payment_handler(handler: PaymentHandler) -> None:
    if handler not in _handlers:
        _handlers.append(handler)


@dataclasses.dataclass(frozen=True)
class Dispatch:
    claimed: bool
    failed: bool  # a handler raised: the event is worth a retry from Square


def dispatch(order_id: str, payment_id: str, paid_at: datetime.datetime | None,
             amount_cents: int | None) -> Dispatch:
    """Offer the payment to each handler; one handler's crash costs no other."""
    failed = False
    for handler in list(_handlers):
        try:
            if handler(order_id, payment_id, paid_at, amount_cents):
                return Dispatch(claimed=True, failed=failed)
        except Exception:
            logger.exception("Payment handler %s failed for order %s",
                             getattr(handler, "__name__", handler), order_id)
            failed = True
    return Dispatch(claimed=False, failed=failed)
