import datetime
from decimal import Decimal
from unittest import mock

from audience.models import Member, MembershipTerm, MembershipTier
from boxoffice.gateway import OrderData, Tender
from boxoffice.memberships import order_sources
from boxoffice.models import MembershipSale
from django.core import mail
from django.test import TestCase

from join.models import MembershipOrder
from join.source import SOURCE
from join.tests.factories import make_order

PAID_AT = datetime.datetime(2026, 10, 26, 15, 0, tzinfo=datetime.timezone.utc)


class SourceTestCase(TestCase):
    def ok_sale(self):
        tier = MembershipTier.objects.get(slug="individual")
        member = Member.objects.create(first_name="Ann", last_name="Lee",
                                       email="ann@example.com")
        term = MembershipTerm.objects.create(
            member=member, tier=tier, started_on=datetime.date(2026, 10, 26),
            expires_on=datetime.date(2027, 10, 25), price_paid=Decimal("60"))
        sale = MembershipSale.objects.create(
            order_id="SQ-1", status="OK", term=term, tier=tier, paid_at=PAID_AT)
        data = OrderData(order_id="SQ-1", closed_at=None, lines=(),
                         tenders=(Tender("P7", "CAPTURED", "CARD", 6000),))
        return sale, data


class BuyerForTests(SourceTestCase):
    def test_pending_order_carries_the_typed_names(self):
        make_order(first_name="Mary Ann", last_name="van Dyke", square_order_id="SQ-1")
        buyer = SOURCE.buyer_for("SQ-1")
        self.assertEqual(
            (buyer.display_name, buyer.first_name, buyer.last_name, buyer.email,
             buyer.phone),
            ("Mary Ann van Dyke", "Mary Ann", "van Dyke", "ann@example.com", ""))

    def test_failed_and_paid_orders_still_answer(self):
        make_order(status="FAILED", square_order_id="SQ-1")
        make_order(status="PAID", square_order_id="SQ-2")
        self.assertIsNotNone(SOURCE.buyer_for("SQ-1"))
        self.assertIsNotNone(SOURCE.buyer_for("SQ-2"))

    def test_unknown_or_abandoned_is_none(self):
        make_order(status="ABANDONED")
        self.assertIsNone(SOURCE.buyer_for("SQ-1"))
        self.assertIsNone(SOURCE.buyer_for("nope"))


class RecordTests(SourceTestCase):
    def test_ok_sale_marks_paid_stores_payment_and_emails_once(self):
        order = make_order(square_order_id="SQ-1")
        sale, data = self.ok_sale()
        SOURCE.record("SQ-1", sale, data)
        SOURCE.record("SQ-1", sale, data)
        order.refresh_from_db()
        self.assertEqual(
            (order.status, order.term, order.sale, order.paid_at,
             order.square_payment_id, order.error),
            ("PAID", sale.term, sale, PAID_AT, "P7", ""))
        self.assertEqual(len(mail.outbox), 1)

    def test_ok_sale_without_an_order_keeps_the_payment_blank(self):
        order = make_order(square_order_id="SQ-1")
        sale, _ = self.ok_sale()
        SOURCE.record("SQ-1", sale, None)
        order.refresh_from_db()
        self.assertEqual((order.status, order.square_payment_id), ("PAID", ""))

    def test_failed_sale_marks_failed_without_email(self):
        order = make_order(square_order_id="SQ-1")
        sale = MembershipSale.objects.create(
            order_id="SQ-1", status="FAILED", error="Current term never expires")
        SOURCE.record("SQ-1", sale, None)
        order.refresh_from_db()
        self.assertEqual((order.status, order.error, order.sale),
                         ("FAILED", "Current term never expires", sale))
        self.assertEqual(mail.outbox, [])

    def test_failed_after_paid_never_downgrades(self):
        order = make_order(square_order_id="SQ-1", status="PAID")
        sale = MembershipSale.objects.create(
            order_id="SQ-1", status="FAILED", error="late news")
        SOURCE.record("SQ-1", sale, None)
        order.refresh_from_db()
        self.assertEqual((order.status, order.error), ("PAID", ""))

    def test_unknown_order_is_ignored(self):
        sale, data = self.ok_sale()
        SOURCE.record("SQ-1", sale, data)  # no row
        self.assertEqual((MembershipOrder.objects.count(), len(mail.outbox)), (0, 0))

    def test_failed_email_leaves_the_order_paid(self):
        make_order(square_order_id="SQ-1")
        sale, data = self.ok_sale()
        with mock.patch("join.source.send_welcome", side_effect=RuntimeError("smtp")), \
                self.assertLogs("join.source", "ERROR"):
            SOURCE.record("SQ-1", sale, data)
        self.assertEqual(MembershipOrder.objects.get().status, "PAID")


class RegistrationTests(TestCase):
    def test_source_is_registered_at_startup(self):
        self.assertIn(SOURCE, order_sources())
