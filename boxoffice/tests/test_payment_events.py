import datetime
from unittest import mock

from boxoffice.payment_events import Dispatch, dispatch, register_payment_handler
from django.test import SimpleTestCase

LOGGER = "boxoffice.payment_events"
PAID_AT = datetime.datetime(2026, 10, 3, 3, 12, tzinfo=datetime.timezone.utc)


class DispatchTests(SimpleTestCase):
    def setUp(self) -> None:
        self.handlers: list = []
        self.enterContext(mock.patch("boxoffice.payment_events._handlers",
                                     self.handlers))

    def test_handlers_run_in_order_and_stop_at_the_first_claim(self) -> None:
        calls = []

        def first(order_id, payment_id, paid_at, amount_cents):
            calls.append(("first", order_id, payment_id, paid_at, amount_cents))
            return False

        def second(order_id, payment_id, paid_at, amount_cents):
            calls.append(("second", order_id))
            return True

        def third(order_id, payment_id, paid_at, amount_cents):
            calls.append(("third", order_id))
            return True

        for handler in (first, second, third):
            register_payment_handler(handler)
        self.assertEqual(dispatch("O1", "P1", PAID_AT, 1600),
                         Dispatch(claimed=True, failed=False))
        self.assertEqual(calls, [("first", "O1", "P1", PAID_AT, 1600),
                                 ("second", "O1")])

    def test_unclaimed_when_no_handler_wants_it(self) -> None:
        register_payment_handler(lambda *a: False)
        self.assertEqual(dispatch("O1", "P1", None, None), Dispatch(False, False))

    def test_a_crashing_handler_is_logged_and_the_rest_still_run(self) -> None:
        seen = []

        def crash(order_id, payment_id, paid_at, amount_cents):
            raise RuntimeError("boom")

        def claim(order_id, payment_id, paid_at, amount_cents):
            seen.append(order_id)
            return True

        register_payment_handler(crash)
        register_payment_handler(claim)
        with self.assertLogs(LOGGER, "ERROR") as logs:
            result = dispatch("O1", "P1", None, None)
        self.assertEqual(result, Dispatch(claimed=True, failed=True))
        self.assertEqual(seen, ["O1"])
        self.assertIn("boom", logs.output[0])

    def test_registering_twice_runs_once(self) -> None:
        calls = []

        def handler(order_id, payment_id, paid_at, amount_cents):
            calls.append(order_id)
            return False

        register_payment_handler(handler)
        register_payment_handler(handler)
        dispatch("O1", "P1", None, None)
        self.assertEqual(calls, ["O1"])


class ReversalDispatchTests(SimpleTestCase):
    """Refunds and disputes reach handlers the same way payments do."""

    def setUp(self) -> None:
        self.refund_handlers: list = []
        self.dispute_handlers: list = []
        self.enterContext(mock.patch("boxoffice.payment_events._refund_handlers",
                                     self.refund_handlers))
        self.enterContext(mock.patch("boxoffice.payment_events._dispute_handlers",
                                     self.dispute_handlers))

    def test_refund_stops_at_the_first_claim(self) -> None:
        from boxoffice.payment_events import dispatch_refund, register_refund_handler
        calls = []

        def first(payment_id, refund_id, refunded_at, amount_cents):
            calls.append(("first", payment_id, refund_id, refunded_at, amount_cents))
            return False

        def second(payment_id, refund_id, refunded_at, amount_cents):
            calls.append(("second", payment_id))
            return True

        def third(*args):
            calls.append(("third",))
            return True

        for handler in (first, second, third):
            register_refund_handler(handler)
        self.assertEqual(dispatch_refund("P1", "R1", PAID_AT, 1600),
                         Dispatch(claimed=True, failed=False))
        self.assertEqual(calls, [("first", "P1", "R1", PAID_AT, 1600),
                                 ("second", "P1")])

    def test_refund_handler_crash_is_logged_and_asks_for_retry(self) -> None:
        from boxoffice.payment_events import dispatch_refund, register_refund_handler

        def crash(*args):
            raise RuntimeError("down")

        register_refund_handler(crash)
        with self.assertLogs(LOGGER, "ERROR"):
            result = dispatch_refund("P1", "R1", PAID_AT, 1600)
        self.assertEqual(result, Dispatch(claimed=False, failed=True))

    def test_dispute_reaches_handlers(self) -> None:
        from boxoffice.payment_events import (dispatch_dispute,
                                              register_dispute_handler)
        calls = []

        def handler(payment_id, dispute_id, state, reason):
            calls.append((payment_id, dispute_id, state, reason))
            return True

        register_dispute_handler(handler)
        self.assertEqual(dispatch_dispute("P1", "D1", "EVIDENCE_REQUIRED", "FRAUD"),
                         Dispatch(claimed=True, failed=False))
        self.assertEqual(calls, [("P1", "D1", "EVIDENCE_REQUIRED", "FRAUD")])
