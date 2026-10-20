from unittest import mock

from boxoffice.gateway import GatewayError, InvalidPhone
from boxoffice.tests.fakes import FakeGateway
from django.test import TestCase, override_settings
from django.utils import timezone

from tickets.models import TicketOrder
from tickets.orders import Refused, start
from tickets.tests.factories import make_live_item, make_showtime

BUYER = {"name": "Ann Lee", "email": " Ann@Example.com", "phone": "207-555-0100"}


class StartTests(TestCase):
    def setUp(self):
        self.st = make_showtime()  # 19:00, a week out: evening prices
        # Real time: the new order's created_at must sit inside the hold window.
        self.now = timezone.now()

    def _start(self, quantities, gateway):
        return start(
            self.st, quantities=quantities, now=self.now, gateway=gateway, **BUYER
        )

    def test_start_creates_pending_order_and_link(self):
        gw = FakeGateway()
        make_live_item(self.st.engagement)
        order = self._start({"adult": 2, "senior": 0, "child": 1}, gw)
        order.refresh_from_db()
        self.assertEqual(order.status, "PENDING")
        self.assertEqual(order.email, "ann@example.com")
        self.assertEqual(order.total_cents, 2200)
        self.assertEqual(
            sorted(order.lines.values_list("tier", "quantity", "unit_cents")),
            [("adult", 2, 800), ("child", 1, 600)],  # no zero line
        )
        self.assertEqual(
            sorted(order.lines.values_list("tier", "square_variation_id")),
            [("adult", "var-adult"), ("child", "var-child")],
        )
        self.assertEqual(order.square_order_id, "SQ-1")
        self.assertEqual(order.square_checkout_url, "https://square.link/u/1")
        self.assertEqual(gw.calls[0][0], "create_payment_link")
        spec = gw.calls[0][1]["spec"]
        self.assertEqual(spec.reference, order.number)
        self.assertEqual(
            [line.variation_id for line in spec.lines], ["var-adult", "var-child"]
        )

    def test_gateway_error_marks_failed(self):
        gw = FakeGateway(fail_with=GatewayError("down"))
        make_live_item(self.st.engagement)
        order = self._start({"adult": 1}, gw)
        order.refresh_from_db()
        self.assertEqual(
            (order.status, order.error, order.square_order_id), ("FAILED", "down", "")
        )

    def test_rejected_phone_retries_once_without_the_prefill(self):
        gw = FakeGateway(reject_phone=True)
        make_live_item(self.st.engagement)
        order = self._start({"adult": 1}, gw)
        order.refresh_from_db()
        self.assertEqual((order.status, order.error), ("PENDING", ""))
        self.assertEqual(order.square_order_id, "SQ-1")
        self.assertEqual(order.phone, "207-555-0100")  # kept for staff
        calls = [c for c in gw.calls if c[0] == "create_payment_link"]
        self.assertEqual(len(calls), 2)
        first, second = calls[0][1]["spec"], calls[1][1]["spec"]
        self.assertEqual(first.buyer_phone, "+12075550100")
        self.assertEqual(second.buyer_phone, "")
        self.assertEqual(second.buyer_email, first.buyer_email)
        self.assertEqual(second.lines, first.lines)
        # A reused key with a different body is refused by Square.
        self.assertNotEqual(second.idempotency_key, first.idempotency_key)

    def test_rejected_phone_then_another_error_marks_failed(self):
        gw = FakeGateway(reject_phone=True)
        make_live_item(self.st.engagement)
        with mock.patch.object(
            gw, "create_payment_link",
            side_effect=[InvalidPhone("INVALID_PHONE_NUMBER"), GatewayError("down")],
        ):
            order = self._start({"adult": 1}, gw)
        order.refresh_from_db()
        self.assertEqual((order.status, order.error), ("FAILED", "down"))

    def test_refuses_when_short_or_zero(self):
        make_live_item(self.st.engagement)
        self.st.online_allowance = 2
        self.st.save()
        with self.assertRaises(Refused) as cm:
            self._start({"adult": 3}, FakeGateway())
        self.assertEqual(cm.exception.reason, "sold_out")
        with self.assertRaises(Refused) as cm:
            self._start({"adult": 0, "senior": 0, "child": 0}, FakeGateway())
        self.assertEqual(cm.exception.reason, "quantity")
        self.assertEqual(TicketOrder.objects.count(), 0)

    def test_takes_exactly_the_remaining_seats(self):
        make_live_item(self.st.engagement)
        self.st.online_allowance = 2
        self.st.save()
        self._start({"adult": 2}, FakeGateway())
        with self.assertRaises(Refused) as cm:
            self._start({"adult": 1}, FakeGateway())
        self.assertEqual(cm.exception.reason, "sold_out")

    def test_refuses_without_live_item(self):
        gw = FakeGateway()
        with self.assertRaises(Refused) as cm:
            self._start({"adult": 1}, gw)
        self.assertEqual(cm.exception.reason, "no_item")
        self.assertEqual(gw.calls, [])
        self.assertEqual(TicketOrder.objects.count(), 0)

    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_refuses_when_square_disabled(self):
        make_live_item(self.st.engagement)
        with self.assertRaises(Refused) as cm:
            self._start({"adult": 1}, None)
        self.assertEqual(cm.exception.reason, "disabled")
        self.assertEqual(TicketOrder.objects.count(), 0)
