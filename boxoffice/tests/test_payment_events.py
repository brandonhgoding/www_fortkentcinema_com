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

        def first(order_id, payment_id, paid_at):
            calls.append(("first", order_id, payment_id, paid_at))
            return False

        def second(order_id, payment_id, paid_at):
            calls.append(("second", order_id))
            return True

        def third(order_id, payment_id, paid_at):
            calls.append(("third", order_id))
            return True

        for handler in (first, second, third):
            register_payment_handler(handler)
        self.assertEqual(dispatch("O1", "P1", PAID_AT),
                         Dispatch(claimed=True, failed=False))
        self.assertEqual(calls, [("first", "O1", "P1", PAID_AT), ("second", "O1")])

    def test_unclaimed_when_no_handler_wants_it(self) -> None:
        register_payment_handler(lambda *a: False)
        self.assertEqual(dispatch("O1", "P1", None), Dispatch(False, False))

    def test_a_crashing_handler_is_logged_and_the_rest_still_run(self) -> None:
        seen = []

        def crash(order_id, payment_id, paid_at):
            raise RuntimeError("boom")

        def claim(order_id, payment_id, paid_at):
            seen.append(order_id)
            return True

        register_payment_handler(crash)
        register_payment_handler(claim)
        with self.assertLogs(LOGGER, "ERROR") as logs:
            result = dispatch("O1", "P1", None)
        self.assertEqual(result, Dispatch(claimed=True, failed=True))
        self.assertEqual(seen, ["O1"])
        self.assertIn("boom", logs.output[0])

    def test_registering_twice_runs_once(self) -> None:
        calls = []

        def handler(order_id, payment_id, paid_at):
            calls.append(order_id)
            return False

        register_payment_handler(handler)
        register_payment_handler(handler)
        dispatch("O1", "P1", None)
        self.assertEqual(calls, ["O1"])
