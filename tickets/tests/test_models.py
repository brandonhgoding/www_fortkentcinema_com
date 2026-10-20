from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import SimpleTestCase, TestCase

from tickets.models import TicketLine, new_number, new_token, split_name
from tickets.tests.factories import make_order, make_showtime


class NumberAndTokenTests(SimpleTestCase):
    def test_number_shape(self):
        n = new_number()
        self.assertRegex(n, r"^FK-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{5}$")

    def test_token_is_long_and_url_safe(self):
        self.assertRegex(new_token(), r"^[A-Za-z0-9_-]{43}$")


class SplitNameTests(SimpleTestCase):
    def test_first_word_then_the_rest(self):
        self.assertEqual(split_name("Ann Lee"), ("Ann", "Lee"))
        self.assertEqual(split_name("Mary Ann Smith"), ("Mary", "Ann Smith"))

    def test_single_word_has_no_family_name(self):
        self.assertEqual(split_name("Brandon"), ("Brandon", ""))
        self.assertEqual(split_name("  Brandon  "), ("Brandon", ""))
        self.assertEqual(split_name(""), ("", ""))


class OrderModelTests(TestCase):
    def setUp(self):
        self.st = make_showtime()

    def test_name_joins_first_and_last(self):
        order = make_order(self.st, first_name="Ann", last_name="Lee")
        self.assertEqual(order.name, "Ann Lee")
        self.assertEqual(order.square_customer_id, "")
        self.assertEqual(make_order(self.st, first_name="Cher", last_name="").name,
                         "Cher")

    def test_defaults_on_create(self):
        order = make_order(self.st)
        self.assertEqual(order.status, "PENDING")
        self.assertTrue(order.number.startswith("FK-"))
        self.assertEqual(len(order.token), 43)

    def test_is_holding_inside_window_only(self):
        order = make_order(self.st)
        self.assertTrue(order.is_holding(order.created_at + timedelta(minutes=19)))
        self.assertFalse(order.is_holding(order.created_at + timedelta(minutes=21)))
        order.status = "PAID"
        self.assertFalse(order.is_holding(order.created_at))

    def test_counts_as_sold(self):
        self.assertTrue(make_order(self.st, status="PAID").counts_as_sold)
        failed_paid = make_order(self.st, status="FAILED", square_payment_id="P1")
        self.assertTrue(failed_paid.counts_as_sold)
        self.assertFalse(make_order(self.st, status="FAILED").counts_as_sold)
        self.assertFalse(make_order(self.st, status="REFUNDED").counts_as_sold)

    def test_breakdown_and_total(self):
        order = make_order(self.st, lines={"child": 1, "adult": 2})
        self.assertEqual(order.breakdown, "2 adult, 1 child")
        self.assertEqual(order.total_dollars, Decimal("22.00"))

    def test_showtime_with_orders_is_protected(self):
        make_order(self.st)
        with self.assertRaises(ProtectedError):
            self.st.delete()

    def test_square_order_id_unique_when_set_blank_allowed_twice(self):
        make_order(self.st, square_order_id="")
        make_order(self.st, square_order_id="")
        make_order(self.st, square_order_id="SQ1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_order(self.st, square_order_id="SQ1")

    def test_email_is_stripped_and_lowercased_on_save(self):
        order = make_order(self.st, email=" Ann@Example.com")
        order.refresh_from_db()
        self.assertEqual(order.email, "ann@example.com")

    def test_zero_quantity_line_is_rejected(self):
        order = make_order(self.st)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TicketLine.objects.create(
                order=order,
                tier="child",
                quantity=0,
                unit_cents=600,
                square_variation_id="VAR-child",
            )
