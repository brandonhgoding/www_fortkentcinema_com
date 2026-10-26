from django.db import IntegrityError
from django.test import TestCase

from join.tests.factories import make_order


class MembershipOrderTests(TestCase):
    def test_defaults(self):
        order = make_order()
        self.assertRegex(order.number, r"^FKM-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{5}$")
        self.assertEqual(len(order.token), 43)
        self.assertEqual((order.status, order.total_cents, order.name, str(order)),
                         ("PENDING", 6000, "Ann Lee", order.number))
        self.assertEqual(str(order.total_dollars), "60")

    def test_email_is_normalised(self):
        order = make_order(email=" Ann@Example.com ")
        self.assertEqual(order.email, "ann@example.com")

    def test_one_order_per_square_order(self):
        make_order(square_order_id="SQ-9")
        with self.assertRaises(IntegrityError):
            make_order(square_order_id="SQ-9")

    def test_blank_square_order_ids_may_repeat(self):
        make_order(status="ABANDONED")
        make_order(status="ABANDONED")
