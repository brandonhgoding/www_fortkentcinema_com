from unittest import mock

from audience.models import MembershipTier
from boxoffice.gateway import GatewayError
from boxoffice.tests.fakes import FakeGateway
from django.test import TestCase

from join.models import MembershipOrder
from join.orders import NotSoldOnline, start
from join.tests.factories import BUYER, set_variation


class StartTests(TestCase):
    def setUp(self):
        # join:order arrives with the views (Task 9); until then, its path.
        patcher = mock.patch("join.spec.reverse", return_value="/membership/order/T/")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_start_creates_pending_order_customer_and_link(self):
        gw = FakeGateway()
        tier = set_variation()
        order = start(tier, gateway=gw, **{**BUYER, "email": " Ann@Example.com"})
        order.refresh_from_db()
        self.assertEqual(
            (order.status, order.email, order.total_cents, order.tier,
             order.square_order_id, order.square_checkout_url,
             order.square_customer_id),
            ("PENDING", "ann@example.com", 6000, tier, "SQ-1",
             "https://square.link/u/1", "C-1"))
        self.assertEqual([c[0] for c in gw.calls],
                         ["find_customer", "create_customer", "create_payment_link"])
        self.assertEqual(gw.customers["C-1"], {
            "given_name": "Ann", "family_name": "Lee",
            "email": "ann@example.com", "phone": ""})
        spec = gw.calls[-1][1]["spec"]
        self.assertEqual(
            (spec.reference, spec.lines[0].variation_id, spec.lines[0].unit_cents,
             spec.customer_id),
            (order.number, "VAR-IND", 6000, "C-1"))

    def test_gateway_failure_abandons_the_order(self):
        tier = set_variation()
        order = start(tier, gateway=FakeGateway(fail_with=GatewayError("boom")),
                      **BUYER)
        self.assertEqual((order.status, order.error, order.square_order_id),
                         ("ABANDONED", "boom", ""))

    def test_tier_without_a_variation_is_refused_before_saving(self):
        tier = MembershipTier.objects.get(slug="individual")
        with self.assertRaises(NotSoldOnline):
            start(tier, gateway=FakeGateway(), **BUYER)
        self.assertEqual(MembershipOrder.objects.count(), 0)

    def test_unlisted_tier_is_refused(self):
        tier = set_variation()
        tier.show_on_membership_page = False
        tier.save()
        with self.assertRaises(NotSoldOnline):
            start(tier, gateway=FakeGateway(), **BUYER)
        self.assertEqual(MembershipOrder.objects.count(), 0)
