import datetime
from io import StringIO
from unittest import mock

from boxoffice.gateway import GatewayError
from boxoffice.tests.fakes import FakeGateway
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from tickets.orders import confirm_payment, expire_stale, recover_pending, resend, start
from tickets.tests.factories import age, make_live_item, make_order, make_showtime

PAID_AT = datetime.datetime(2026, 10, 3, 3, 12, tzinfo=datetime.timezone.utc)
BUYER = {"name": "Ann Lee", "email": "ann@example.com", "phone": "207-555-0100"}


class ConfirmTests(TestCase):
    def setUp(self):
        self.st = make_showtime()

    def test_confirm_marks_paid_and_emails_once(self):
        order = make_order(self.st, square_order_id="SQ1")
        confirm_payment("SQ1", "P1", paid_at=PAID_AT)
        confirm_payment("SQ1", "P1", paid_at=PAID_AT)
        order.refresh_from_db()
        self.assertEqual(
            (order.status, order.square_payment_id, order.paid_at),
            ("PAID", "P1", PAID_AT),
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_paid_at_defaults_to_now(self):
        make_order(self.st, square_order_id="SQ1")
        before = timezone.now()
        order = confirm_payment("SQ1", "P1")
        self.assertGreaterEqual(order.paid_at, before)

    def test_unknown_order_is_ignored(self):
        self.assertIsNone(confirm_payment("nope", "P1"))
        self.assertEqual(len(mail.outbox), 0)

    def test_refunded_order_is_unchanged(self):
        make_order(
            self.st, status="REFUNDED", square_order_id="SQ1", square_payment_id="P0"
        )
        order = confirm_payment("SQ1", "P1")
        self.assertEqual((order.status, order.square_payment_id), ("REFUNDED", "P0"))
        self.assertEqual(len(mail.outbox), 0)

    def test_expired_and_cancelled_showtime_still_pay(self):
        self.st.is_cancelled = True
        self.st.save()
        make_order(self.st, status="EXPIRED", square_order_id="SQ1")
        self.assertEqual(confirm_payment("SQ1", "P1").status, "PAID")
        self.assertEqual(len(mail.outbox), 1)

    def test_failed_without_payment_pays(self):
        make_order(self.st, status="FAILED", square_order_id="SQ1", error="x")
        self.assertEqual(confirm_payment("SQ1", "P1").status, "PAID")

    def test_failed_with_payment_is_unchanged(self):
        make_order(
            self.st,
            status="FAILED",
            square_order_id="SQ1",
            square_payment_id="P1",
            error="Ticket email failed",
        )
        self.assertEqual(confirm_payment("SQ1", "P1").status, "FAILED")
        self.assertEqual(len(mail.outbox), 0)

    def test_mail_failure_leaves_failed_with_payment_and_resend_fixes_it(self):
        make_order(self.st, square_order_id="SQ1")
        with (
            mock.patch("tickets.orders.send_ticket", side_effect=OSError("smtp")),
            self.assertLogs("tickets.orders", "ERROR"),
        ):
            order = confirm_payment("SQ1", "P1")
        order.refresh_from_db()
        self.assertEqual((order.status, order.square_payment_id), ("FAILED", "P1"))
        self.assertIn("Ticket email failed", order.error)
        self.assertEqual(len(mail.outbox), 0)
        order = resend(order)
        order.refresh_from_db()
        self.assertEqual((order.status, order.error), ("PAID", ""))
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_ignores_orders_without_payment(self):
        order = make_order(self.st, status="FAILED", error="down")
        self.assertEqual(resend(order).status, "FAILED")
        self.assertEqual(len(mail.outbox), 0)


class RecoveryTests(TestCase):
    def setUp(self):
        self.st = make_showtime()
        self.gw = FakeGateway()
        make_live_item(self.st.engagement)

    def _start(self):
        return start(
            self.st,
            quantities={"adult": 1},
            now=timezone.now(),
            gateway=self.gw,
            **BUYER,
        )

    def test_recover_pending_finds_the_tender(self):
        order = self._start()
        self.gw.pay(order.square_order_id, "P3")
        order = recover_pending(order, gateway=self.gw)
        self.assertEqual((order.status, order.square_payment_id), ("PAID", "P3"))
        self.assertEqual(len(mail.outbox), 1)

    def test_recover_pending_leaves_unpaid_order(self):
        order = self._start()
        self.assertEqual(recover_pending(order, gateway=self.gw).status, "PENDING")
        self.assertEqual(len(mail.outbox), 0)

    def test_recover_pending_logs_gateway_error(self):
        order = self._start()
        self.gw.fail_with = GatewayError("down")
        with self.assertLogs("tickets.orders", "WARNING"):
            self.assertEqual(recover_pending(order, gateway=self.gw).status, "PENDING")

    def test_expire_stale(self):
        paid_late, unpaid, young = self._start(), self._start(), self._start()
        age(paid_late, 25)
        age(unpaid, 25)
        self.gw.pay(paid_late.square_order_id)
        self.assertEqual(expire_stale(timezone.now(), gateway=self.gw), 1)
        statuses = [
            o.status for o in (paid_late, unpaid, young) if o.refresh_from_db() is None
        ]
        self.assertEqual(statuses, ["PAID", "EXPIRED", "PENDING"])

    def test_expire_stale_without_square_order(self):
        order = make_order(self.st)
        age(order, 25)
        self.assertEqual(expire_stale(timezone.now(), gateway=self.gw), 1)
        order.refresh_from_db()
        self.assertEqual(order.status, "EXPIRED")

    def test_expire_leaves_pending_on_gateway_error(self):
        order = self._start()
        age(order, 25)
        self.gw.fail_with = GatewayError("down")
        with self.assertLogs("tickets.orders", "WARNING"):
            self.assertEqual(expire_stale(timezone.now(), gateway=self.gw), 0)
        order.refresh_from_db()
        self.assertEqual(order.status, "PENDING")

    def test_command_prints_count(self):
        order = make_order(self.st)
        age(order, 25)
        out = StringIO()
        with mock.patch("tickets.orders.get_gateway", return_value=self.gw):
            call_command("expire_ticket_orders", stdout=out)
        self.assertEqual(out.getvalue().strip(), "Expired 1 order(s)")
