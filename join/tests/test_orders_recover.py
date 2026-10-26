from audience.models import Member, MembershipTier
from boxoffice.gateway import GatewayError
from boxoffice.models import MembershipSale
from boxoffice.tests.fakes import FakeGateway
from django.core import mail
from django.test import TestCase

from join.orders import recover_pending, start
from join.tests.factories import BUYER, make_order, set_variation
from join.tests.helpers import patch_reverse


class RecoverPendingTests(TestCase):
    def setUp(self):
        for target in ("join.spec.reverse", "join.mail.reverse"):
            patcher = patch_reverse(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.gw = FakeGateway()

    def started(self):
        set_variation()
        return start(MembershipTier.objects.get(slug="individual"),
                     gateway=self.gw, **BUYER)

    def test_paid_order_is_entered_by_recovery(self):
        order = self.started()
        self.gw.pay(order.square_order_id, "P2")
        recover_pending(order, self.gw)
        self.assertEqual((order.status, order.square_payment_id), ("PAID", "P2"))
        self.assertTrue(Member.objects.filter(email="ann@example.com").exists())
        self.assertEqual(MembershipSale.objects.get().source, "WEBSITE")
        self.assertEqual(len(mail.outbox), 1)

    def test_unpaid_order_stays_pending(self):
        order = self.started()
        recover_pending(order, self.gw)
        self.assertEqual((order.status, MembershipSale.objects.count()),
                         ("PENDING", 0))

    def test_square_unreachable_is_logged_and_harmless(self):
        order = self.started()
        with self.assertLogs("join.orders", "WARNING"):
            recover_pending(order, FakeGateway(fail_with=GatewayError("down")))
        self.assertEqual(order.status, "PENDING")

    def test_square_off_is_harmless(self):
        order = self.started()
        recover_pending(order, None)
        self.assertEqual(order.status, "PENDING")

    def test_only_pending_orders_ask_square(self):
        order = make_order(status="PAID")
        gw = FakeGateway()
        recover_pending(order, gw)
        self.assertEqual(gw.calls, [])
