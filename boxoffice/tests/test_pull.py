import dataclasses
import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from boxoffice.gateway import GatewayError, OrderData, OrderLine, Tender
from boxoffice.models import SaleLine, SalesPull, SquareVariation
from boxoffice.pull import business_date, day_bounds, mark_refunded, pull_day
from boxoffice.sync import live_item, push
from boxoffice.tests.fakes import FakeGateway
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.test import SimpleTestCase, TestCase, override_settings
from tickets.models import TicketOrder
from tickets.spec import checkout_spec
from tickets.tests.factories import make_order

LOGGER = "boxoffice.pull"
DAY = datetime.date(2026, 10, 9)
TICKETS = "CAT-TICKETS"


def make_eng(**over):
    screen = Screen.objects.get_or_create(name="Screen 1", capacity=50)[0]
    defaults = dict(
        screen=screen,
        start_date=datetime.date(2026, 10, 9),
        end_date=datetime.date(2026, 10, 15),
        status="CONFIRMED",
    )
    defaults.update(over)
    eng = Engagement.objects.create(**defaults)
    film = Film.objects.get_or_create(title="Dune")[0]
    EngagementFilm.objects.create(engagement=eng, film=film, position=1)
    return eng


def at_eastern(*parts) -> datetime.datetime:
    return datetime.datetime(*parts, tzinfo=ZoneInfo("America/New_York"))


def order(order_id, closed_at, *lines) -> OrderData:
    return OrderData(order_id=order_id, closed_at=closed_at, lines=tuple(lines))


def line(uid, name, variation_name="", catalog_object_id="", quantity=1,
         gross_cents=800) -> OrderLine:
    return OrderLine(uid=uid, name=name, variation_name=variation_name,
                     catalog_object_id=catalog_object_id, quantity=quantity,
                     gross_cents=gross_cents)


class BusinessDateTests(SimpleTestCase):
    def test_eastern_calendar_day(self) -> None:
        # 03:30 UTC on Oct 10 is 23:30 Eastern on Oct 9
        self.assertEqual(
            business_date(datetime.datetime(2026, 10, 10, 3, 30, tzinfo=datetime.UTC)),
            datetime.date(2026, 10, 9))

    def test_day_bounds_are_eastern_midnights(self) -> None:
        start, end = day_bounds(datetime.date(2026, 10, 9))
        self.assertEqual(start.isoformat(), "2026-10-09T00:00:00-04:00")
        self.assertEqual(end.isoformat(), "2026-10-10T00:00:00-04:00")


@override_settings(SQUARE_TICKET_CATEGORY_ID=TICKETS)
class PullDayTests(TestCase):
    def setUp(self) -> None:
        self.gw = FakeGateway()
        self.eng = make_eng()
        push(self.eng, self.gw)
        self.gw.calls.clear()
        self.adult_id = live_item(self.eng).variations.get(tier="adult").square_id

    def test_lines_stored_and_attributed(self) -> None:
        gw = self.gw
        gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                           line("L1", "Dune", "Adult", self.adult_id, 2, 1600),
                           line("L2", "Popcorn", "", "VPOP", 1, 500))]
        pull = pull_day(datetime.date(2026, 10, 9), gw)
        self.assertEqual((pull.status, pull.orders, pull.lines), ("OK", 1, 2))
        ticket = SaleLine.objects.get(line_uid="L1")
        self.assertEqual((ticket.engagement_id, ticket.quantity, ticket.gross_cents),
                         (self.eng.pk, 2, 1600))
        self.assertIsNone(SaleLine.objects.get(line_uid="L2").engagement)
        self.assertEqual(ticket.variation.square_id, self.adult_id)
        self.assertEqual(ticket.business_date, DAY)
        self.assertEqual(ticket.category_id, TICKETS)
        self.assertIsNotNone(pull.finished_at)
        self.assertEqual(pull.business_date, DAY)

    def test_online_order_line_is_linked_to_its_showtime(self) -> None:
        showtime = Showtime.objects.create(
            engagement=self.eng, screen=self.eng.screen,
            starts_at=at_eastern(2026, 10, 11, 19, 0))
        make_order(showtime, status="PAID", square_order_id="O1")
        self.gw.orders = [
            order("O1", at_eastern(2026, 10, 9, 12, 0),
                  line("L1", "Dune", "Adult", self.adult_id, 2, 1600)),
            order("O2", at_eastern(2026, 10, 9, 19, 5),
                  line("L2", "Dune", "Adult", self.adult_id, 1, 800)),
        ]
        pull_day(datetime.date(2026, 10, 9), self.gw)
        self.assertEqual(SaleLine.objects.get(line_uid="L1").showtime, showtime)
        self.assertIsNone(SaleLine.objects.get(line_uid="L2").showtime)

    def test_unattributed_categories_resolved_in_one_lookup(self) -> None:
        self.gw.categories = {"VPOP": "CAT-SNACKS"}
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "Dune", "Adult", self.adult_id),
                                line("L2", "Popcorn", "", "VPOP"),
                                line("L3", "Popcorn", "", "VPOP"),
                                line("L4", "Mystery", "", "VGONE"))]
        pull_day(DAY, self.gw)
        lookups = [kw for name, kw in self.gw.calls if name == "lookup_categories"]
        self.assertEqual(len(lookups), 1)
        self.assertEqual(sorted(lookups[0]["variation_ids"]), ["VGONE", "VPOP"])
        self.assertEqual(SaleLine.objects.get(line_uid="L2").category_id, "CAT-SNACKS")
        self.assertEqual(SaleLine.objects.get(line_uid="L3").category_id, "CAT-SNACKS")
        self.assertEqual(SaleLine.objects.get(line_uid="L4").category_id, "")

    def test_second_pull_changes_nothing(self) -> None:
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "Dune", "Adult", self.adult_id, 2, 1600),
                                line("L2", "Popcorn", "", "VPOP", 1, 500))]
        pull_day(DAY, self.gw)
        before = list(SaleLine.objects.order_by("pk").values())
        second = pull_day(DAY, self.gw)
        self.assertEqual((second.status, second.orders, second.lines), ("OK", 1, 2))
        self.assertEqual(list(SaleLine.objects.order_by("pk").values()), before)
        self.assertEqual(SalesPull.objects.count(), 2)
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.admissions, 2)

    def test_line_without_catalog_id_is_kept_unattributed(self) -> None:
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 20, 0),
                                line("L9", "Custom amount", "", "", 1, 300))]
        pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.lines), ("OK", 1))
        stored = SaleLine.objects.get(line_uid="L9")
        self.assertEqual(stored.catalog_object_id, "")
        self.assertEqual(stored.category_id, "")
        self.assertIsNone(stored.variation)
        self.assertIsNone(stored.engagement)
        self.assertNotIn("lookup_categories", [name for name, _ in self.gw.calls])

    def test_admissions_recomputed_for_linked_only(self) -> None:
        unlinked = make_eng(admissions=42)
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "Dune", "Adult", self.adult_id, 1, 800)),
                          order("O2", at_eastern(2026, 10, 9, 21, 0),
                                line("L1", "Dune", "Adult", self.adult_id, 1, 800),
                                line("L2", "Popcorn", "", "VPOP", 3, 1500))]
        pull_day(DAY, self.gw)
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.admissions, 2)
        unlinked.refresh_from_db()
        self.assertEqual(unlinked.admissions, 42)

    def test_admissions_count_all_time(self) -> None:
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "Dune", "Adult", self.adult_id, 2, 1600)),
                          order("O2", at_eastern(2026, 10, 10, 19, 5),
                                line("L1", "Dune", "Adult", self.adult_id, 3, 2400))]
        pull_day(DAY, self.gw)
        pull_day(DAY + datetime.timedelta(days=1), self.gw)
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.admissions, 5)

    def test_repull_keeps_attribution_when_variation_is_gone(self) -> None:
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "Dune", "Adult", self.adult_id, 2, 1600))]
        pull_day(DAY, self.gw)
        SquareVariation.objects.filter(square_id=self.adult_id).delete()
        Engagement.objects.filter(pk=self.eng.pk).update(admissions=99)
        second = pull_day(DAY, self.gw)
        self.assertEqual(second.status, "OK")
        stored = SaleLine.objects.get(line_uid="L1")
        self.assertEqual(stored.engagement_id, self.eng.pk)
        self.assertIsNone(stored.variation)
        self.assertEqual(stored.category_id, TICKETS)
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.admissions, 2)

    def test_repull_updates_changed_quantity_and_admissions(self) -> None:
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "Dune", "Adult", self.adult_id, 2, 1600))]
        pull_day(DAY, self.gw)
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "Dune", "Adult", self.adult_id, 3, 2400))]
        pull_day(DAY, self.gw)
        stored = SaleLine.objects.get(line_uid="L1")
        self.assertEqual((stored.quantity, stored.gross_cents), (3, 2400))
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.admissions, 3)

    def test_engagement_losing_lines_is_recomputed(self) -> None:
        other = make_eng()
        push(other, self.gw)
        other_adult = live_item(other).variations.get(tier="adult").square_id
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "Dune", "Adult", self.adult_id, 2, 1600))]
        pull_day(DAY, self.gw)
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "Dune", "Adult", other_adult, 2, 1600))]
        pull_day(DAY, self.gw)
        self.eng.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((self.eng.admissions, other.admissions), (0, 2))

    def test_gateway_failure_writes_failed_row(self) -> None:
        gw = self.gw
        gw.fail_with = GatewayError("down")
        with self.assertLogs(LOGGER, "WARNING"):
            pull = pull_day(datetime.date(2026, 10, 9), gw)
        self.assertEqual((pull.status, pull.error), ("FAILED", "down"))
        self.assertIsNotNone(pull.finished_at)
        self.assertEqual(SalesPull.objects.get().status, SalesPull.Status.FAILED)

    def test_row_is_created_failed_until_the_pull_finishes(self) -> None:
        seen = []

        def search_orders(start, end):
            row = SalesPull.objects.get()
            seen.append((row.status, row.error))
            raise GatewayError("down")

        self.gw.search_orders = search_orders
        with self.assertLogs(LOGGER, "WARNING"):
            pull = pull_day(DAY, self.gw)
        self.assertEqual(seen, [("FAILED", "Pull did not finish")])
        pull.refresh_from_db()
        self.assertEqual((pull.status, pull.error), ("FAILED", "down"))

    def test_successful_pull_clears_the_placeholder_error(self) -> None:
        pull = pull_day(DAY, self.gw)
        pull.refresh_from_db()
        self.assertEqual((pull.status, pull.error), ("OK", ""))

    def test_category_lookup_failure_stores_nothing(self) -> None:
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L2", "Popcorn", "", "VPOP"))]
        with mock.patch.object(self.gw, "lookup_categories",
                               side_effect=GatewayError("catalog down")):
            with self.assertLogs(LOGGER, "WARNING"):
                pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.error), ("FAILED", "catalog down"))
        self.assertFalse(SaleLine.objects.exists())

    def test_unexpected_error_writes_failed_row(self) -> None:
        with mock.patch.object(self.gw, "search_orders",
                               side_effect=ValueError("boom")):
            with self.assertLogs(LOGGER, "ERROR"):
                pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.error), ("FAILED", "ValueError('boom')"))
        self.assertIsNotNone(pull.finished_at)

    def test_order_without_closed_at_is_skipped(self) -> None:
        orders = [order("O0", None, line("L0", "Dune", "Adult", self.adult_id)),
                  order("O1", at_eastern(2026, 10, 9, 19, 5),
                        line("L1", "Dune", "Adult", self.adult_id))]
        with mock.patch.object(self.gw, "search_orders", return_value=orders):
            with self.assertLogs(LOGGER, "WARNING") as logs:
                pull = pull_day(DAY, self.gw)
        self.assertIn("O0", logs.output[0])
        self.assertEqual((pull.status, pull.orders, pull.lines), ("OK", 1, 1))
        self.assertFalse(SaleLine.objects.filter(order_id="O0").exists())

    def test_quiet_day_is_ok_with_zero_counts(self) -> None:
        pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.orders, pull.lines), ("OK", 0, 0))
        self.assertFalse(SaleLine.objects.exists())
        self.assertEqual(self.gw.calls[0][0], "search_orders")
        self.assertEqual(self.gw.calls[0][1]["start"], at_eastern(2026, 10, 9, 0, 0))
        self.assertEqual(self.gw.calls[0][1]["end"], at_eastern(2026, 10, 10, 0, 0))

    # Square leaves a paid payment-link order OPEN (sandbox, 2026-10-19), so the
    # COMPLETED search never sees it; the pull asks for open orders too and
    # dates such a sale by when the buyer paid.

    def link_order(self, quantity: int = 2):
        """A website order with its payment link made; (ticket order, Square id)."""
        showtime = Showtime.objects.create(
            engagement=self.eng, screen=self.eng.screen,
            starts_at=at_eastern(2026, 10, 11, 19, 0))
        ticket_order = make_order(showtime, lines={"adult": quantity})
        link = self.gw.create_payment_link(
            checkout_spec(ticket_order, {"adult": self.adult_id}))
        ticket_order.square_order_id = link.order_id
        ticket_order.save(update_fields=["square_order_id"])
        return ticket_order, link.order_id

    def test_paid_payment_link_order_is_stored_on_its_payment_day(self) -> None:
        ticket_order, order_id = self.link_order(quantity=2)
        self.gw.pay(order_id, paid_at=at_eastern(2026, 10, 9, 12, 0))
        pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.orders, pull.lines), ("OK", 1, 1))
        stored = SaleLine.objects.get(order_id=order_id)
        self.assertEqual(stored.business_date, DAY)
        self.assertIsNone(stored.closed_at)
        self.assertEqual(stored.showtime, ticket_order.showtime)
        self.assertEqual((stored.engagement_id, stored.quantity, stored.gross_cents),
                         (self.eng.pk, 2, 1600))
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.admissions, 2)

    def test_unpaid_payment_link_order_is_not_stored(self) -> None:
        self.link_order()
        pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.orders, pull.lines), ("OK", 0, 0))
        self.assertFalse(SaleLine.objects.exists())

    def test_open_order_without_our_reference_is_not_stored(self) -> None:
        # A register tab left open with a part payment is not a sale yet.
        self.gw.orders = [OrderData(
            "TAB", None, (line("L1", "Dune", "Adult", self.adult_id),),
            paid_at=at_eastern(2026, 10, 9, 20, 0),
            tenders=(Tender("P1", "CAPTURED"),), reference_id="")]
        pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.orders, pull.lines), ("OK", 0, 0))
        self.assertFalse(SaleLine.objects.exists())

    def test_completed_payment_link_order_keeps_its_payment_day(self) -> None:
        # Staff marking the digital fulfillment done closes the order days
        # later; the COMPLETED search then returns it, and it must not move.
        _, order_id = self.link_order()
        self.gw.pay(order_id, paid_at=at_eastern(2026, 10, 9, 12, 0))
        pull_day(DAY, self.gw)
        closed_at = at_eastern(2026, 10, 12, 9, 0)
        self.gw.orders = [dataclasses.replace(o, closed_at=closed_at)
                          if o.order_id == order_id else o for o in self.gw.orders]
        later = pull_day(datetime.date(2026, 10, 12), self.gw)
        self.assertEqual((later.status, later.orders), ("OK", 1))
        stored = SaleLine.objects.get()
        self.assertEqual((stored.business_date, stored.closed_at), (DAY, closed_at))

    def test_pull_counts_paid_online_orders_missing_from_the_ledger(self) -> None:
        # The guard for the day Square stops returning our paid orders: a
        # website order paid on the day with no ledger line after the pull.
        showtime = Showtime.objects.create(
            engagement=self.eng, screen=self.eng.screen,
            starts_at=at_eastern(2026, 10, 11, 19, 0))
        make_order(showtime, status="PAID", square_order_id="SQ-GONE",
                   paid_at=at_eastern(2026, 10, 9, 12, 0))
        make_order(showtime, status="PAID", square_order_id="SQ-OTHER-DAY",
                   paid_at=at_eastern(2026, 10, 10, 12, 0))
        with self.assertLogs(LOGGER, "WARNING") as logs:
            pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.missing_online), ("OK", 1))
        self.assertIn("SQ-GONE", logs.output[0])

    def test_stored_online_orders_are_not_missing(self) -> None:
        _, order_id = self.link_order()
        self.gw.pay(order_id, paid_at=at_eastern(2026, 10, 9, 12, 0))
        pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.missing_online), ("OK", 0))

    def test_long_register_names_are_cut_to_the_ledger_columns(self) -> None:
        # Square allows 512-character item and 255-character variation names;
        # the ledger holds 200 and 80, and Postgres refuses longer (SQLite,
        # which the tests use, does not), which would fail the whole day.
        self.gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                                line("L1", "N" * 300, "V" * 100, "VPOP"))]
        pull = pull_day(DAY, self.gw)
        self.assertEqual((pull.status, pull.lines), ("OK", 1))
        stored = SaleLine.objects.get(line_uid="L1")
        self.assertEqual((len(stored.item_name), len(stored.variation_name)),
                         (200, 80))

    def test_refunded_online_order_is_marked_on_the_next_pull(self) -> None:
        # The refund may land after the lookback stopped re-pulling the sale
        # day; the pull still derives the mark from the order's status so a
        # re-pull never undoes it.
        ticket_order, order_id = self.link_order(quantity=2)
        self.gw.pay(order_id, paid_at=at_eastern(2026, 10, 9, 12, 0))
        pull_day(DAY, self.gw)
        TicketOrder.objects.filter(pk=ticket_order.pk).update(status="REFUNDED")
        pull_day(DAY, self.gw)
        stored = SaleLine.objects.get(order_id=order_id)
        self.assertEqual((stored.quantity, stored.gross_cents,
                          stored.refunded_quantity, stored.refunded_cents),
                         (2, 1600, 2, 1600))
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.admissions, 0)

    def test_mark_refunded_zeroes_the_lines_and_admissions_at_once(self) -> None:
        ticket_order, order_id = self.link_order(quantity=2)
        self.gw.pay(order_id, paid_at=at_eastern(2026, 10, 9, 12, 0))
        pull_day(DAY, self.gw)
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.admissions, 2)
        mark_refunded(order_id)
        stored = SaleLine.objects.get(order_id=order_id)
        self.assertEqual((stored.refunded_quantity, stored.refunded_cents),
                         (2, 1600))
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.admissions, 0)
        mark_refunded("SQ-NOT-PULLED-YET")  # nothing to mark, no error
