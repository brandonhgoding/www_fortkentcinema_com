from unittest import mock

from boxoffice.models import SaleLine
from boxoffice.tests.fakes import FakeGateway
from cinema.models import Engagement
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from tickets.refunds import RefundSummary, refund_order, refund_showtime
from tickets.tests.factories import make_order, make_showtime


def ledger_line(showtime, order_id: str, quantity: int, gross_cents: int) -> SaleLine:
    """What the nightly pull stored for the order, with admissions to match."""
    Engagement.objects.filter(pk=showtime.engagement_id).update(admissions=quantity)
    return SaleLine.objects.create(
        order_id=order_id, line_uid="L1", business_date=timezone.localdate(),
        item_name="Dune", quantity=quantity, gross_cents=gross_cents,
        engagement=showtime.engagement, showtime=showtime)


class RefundOrderTests(TestCase):
    def setUp(self):
        self.st = make_showtime()

    def test_refund_zeroes_the_ledger_lines_and_admissions(self):
        order = make_order(self.st, status="PAID", square_payment_id="P1",
                           square_order_id="SQ-9", lines={"adult": 2})
        line = ledger_line(self.st, "SQ-9", 2, 1600)
        refund_order(order, reason="Showtime cancelled", gateway=FakeGateway())
        line.refresh_from_db()
        self.assertEqual((line.refunded_quantity, line.refunded_cents), (2, 1600))
        self.st.engagement.refresh_from_db()
        self.assertEqual(self.st.engagement.admissions, 0)

    def test_failed_refund_leaves_the_ledger_alone(self):
        order = make_order(self.st, status="PAID", square_payment_id="P1",
                           square_order_id="SQ-9", lines={"adult": 2})
        line = ledger_line(self.st, "SQ-9", 2, 1600)
        refund_order(order, reason="x", gateway=FakeGateway(fail_on={"P1"}))
        line.refresh_from_db()
        self.assertEqual((line.refunded_quantity, line.refunded_cents), (0, 0))
        self.st.engagement.refresh_from_db()
        self.assertEqual(self.st.engagement.admissions, 2)

    def test_refund_order_success(self):
        gw = FakeGateway()
        order = make_order(
            self.st,
            status="PAID",
            square_payment_id="P1",
            lines={"adult": 2, "child": 1},
            error="old",
        )
        order = refund_order(order, reason="Showtime cancelled", gateway=gw)
        order.refresh_from_db()
        self.assertEqual(order.status, "REFUNDED")
        self.assertIsNotNone(order.refunded_at)
        self.assertEqual(order.error, "")
        self.assertEqual(
            gw.calls[0],
            (
                "refund_payment",
                {
                    "payment_id": "P1",
                    "amount_cents": 2200,
                    "idempotency_key": f"refund-{order.number}",
                    "reason": "Showtime cancelled",
                },
            ),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject[:9], "Refunded:")

    def test_failed_with_payment_is_refunded(self):
        gw = FakeGateway()
        order = make_order(self.st, status="FAILED", square_payment_id="P1")
        order = refund_order(order, reason="Showtime cancelled", gateway=gw)
        self.assertEqual(order.status, "REFUNDED")
        self.assertEqual(len(gw.calls), 1)

    def test_second_click_is_a_no_op(self):
        gw = FakeGateway()
        order = make_order(self.st, status="PAID", square_payment_id="P1")
        refund_order(order, reason="Showtime cancelled", gateway=gw)
        order = refund_order(order, reason="Showtime cancelled", gateway=gw)
        self.assertEqual(order.status, "REFUNDED")
        self.assertEqual(len(gw.calls), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_unpaid_orders_are_not_refunded(self):
        gw = FakeGateway()
        for status in ["PENDING", "EXPIRED", "FAILED"]:
            order = make_order(self.st, status=status)
            order = refund_order(order, reason="Showtime cancelled", gateway=gw)
            self.assertEqual(order.status, status)
        self.assertEqual(gw.calls, [])
        self.assertEqual(mail.outbox, [])

    def test_gateway_error_keeps_paid_with_error(self):
        gw = FakeGateway(fail_on={"P1"})
        order = make_order(self.st, status="PAID", square_payment_id="P1")
        order = refund_order(order, reason="Showtime cancelled", gateway=gw)
        order.refresh_from_db()
        self.assertEqual((order.status, order.error), ("PAID", "boom"))
        self.assertIsNone(order.refunded_at)
        self.assertEqual(mail.outbox, [])

    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_refund_without_gateway_records_reason(self):
        order = make_order(self.st, status="PAID", square_payment_id="P1")
        order = refund_order(order, reason="Showtime cancelled")
        order.refresh_from_db()
        self.assertEqual(order.status, "PAID")
        self.assertEqual(order.error, "Square sync disabled: no SQUARE_ACCESS_TOKEN")
        self.assertEqual(mail.outbox, [])

    def test_refund_email_failure_keeps_refunded(self):
        gw = FakeGateway()
        order = make_order(self.st, status="PAID", square_payment_id="P1")
        with (
            mock.patch("tickets.refunds.send_refund", side_effect=OSError("smtp")),
            self.assertLogs("tickets.refunds", "ERROR"),
        ):
            order = refund_order(order, reason="Showtime cancelled", gateway=gw)
        order.refresh_from_db()
        self.assertEqual(order.status, "REFUNDED")
        self.assertIsNotNone(order.refunded_at)
        self.assertEqual(order.error, "Refund email failed: OSError('smtp')")


class RefundShowtimeTests(TestCase):
    def setUp(self):
        self.st = make_showtime()

    def test_refund_showtime_partial_failure(self):
        gw = FakeGateway()
        a = make_order(self.st, status="PAID", square_payment_id="P1")
        b = make_order(self.st, status="PAID", square_payment_id="P2")
        gw.fail_on = {b.square_payment_id}
        self.assertEqual(refund_showtime(self.st, gateway=gw), RefundSummary(1, 1))
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.status, "REFUNDED")
        self.assertEqual((b.status, b.error), ("PAID", "boom"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            [kwargs["reason"] for _, kwargs in gw.calls], ["Showtime cancelled"] * 2
        )

    def test_walks_sold_orders_in_pk_order_and_skips_the_rest(self):
        gw = FakeGateway()
        first = make_order(self.st, status="PAID", square_payment_id="P1")
        make_order(self.st, status="PENDING")
        make_order(self.st, status="FAILED")
        make_order(self.st, status="REFUNDED", square_payment_id="P9")
        third = make_order(self.st, status="FAILED", square_payment_id="P3")
        other = make_order(make_showtime(), status="PAID", square_payment_id="P4")
        summary = refund_showtime(self.st, reason="Projector broke", gateway=gw)
        self.assertEqual(summary, RefundSummary(2, 0))
        self.assertEqual(
            [kwargs["idempotency_key"] for _, kwargs in gw.calls],
            [f"refund-{first.number}", f"refund-{third.number}"],
        )
        self.assertEqual(gw.calls[0][1]["reason"], "Projector broke")
        other.refresh_from_db()
        self.assertEqual(other.status, "PAID")
