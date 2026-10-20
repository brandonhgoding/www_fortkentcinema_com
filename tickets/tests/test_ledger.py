import datetime
from zoneinfo import ZoneInfo

import boxoffice.pull
from boxoffice.payment_events import _handlers
from django.test import TestCase

from tickets.ledger import TicketOrders
from tickets.orders import handle_square_payment
from tickets.tests.factories import make_order, make_showtime

EASTERN = ZoneInfo("America/New_York")


def at(day: int, hour: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, day, hour, tzinfo=EASTERN)


class RegistrationTests(TestCase):
    def test_tickets_is_the_ledger_s_website_source(self) -> None:
        self.assertIsInstance(boxoffice.pull.website, TicketOrders)

    def test_tickets_handles_square_payments_first(self) -> None:
        self.assertEqual(_handlers, [handle_square_payment])


class TicketOrdersTests(TestCase):
    def setUp(self) -> None:
        self.st = make_showtime()
        self.source = TicketOrders()

    def test_refunded_names_orders_refunded_in_full(self) -> None:
        make_order(self.st, status="REFUNDED", square_order_id="SQ-R")
        make_order(self.st, status="PAID", square_order_id="SQ-P")
        self.assertEqual(self.source.refunded(["SQ-R", "SQ-P", "SQ-?"]), {"SQ-R"})

    def test_paid_names_orders_paid_in_the_window(self) -> None:
        make_order(self.st, status="PAID", square_order_id="SQ-1", paid_at=at(9, 12))
        make_order(self.st, status="REFUNDED", square_order_id="SQ-2",
                   paid_at=at(9, 23))
        make_order(self.st, status="PAID", square_order_id="SQ-3", paid_at=at(10, 0))
        make_order(self.st, status="PENDING", square_order_id="SQ-4")
        self.assertEqual(self.source.paid(at(9, 0), at(10, 0)), {"SQ-1", "SQ-2"})


class HandlerTests(TestCase):
    def test_claims_its_own_order_only(self) -> None:
        st = make_showtime()
        order = make_order(st, square_order_id="SQ1")
        self.assertTrue(handle_square_payment("SQ1", "P1", at(3, 3)))
        order.refresh_from_db()
        self.assertEqual((order.status, order.square_payment_id), ("PAID", "P1"))
        self.assertFalse(handle_square_payment("SQ-unknown", "P2", None))
