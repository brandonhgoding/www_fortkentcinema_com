import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from boxoffice.gateway import GatewayError, OrderData, OrderLine
from boxoffice.models import SaleLine, SalesPull
from boxoffice.pull import business_date, day_bounds, pull_day
from boxoffice.sync import live_item, push
from boxoffice.tests.fakes import FakeGateway
from cinema.models import Engagement, EngagementFilm, Film, Screen
from django.test import SimpleTestCase, TestCase, override_settings

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

    def test_gateway_failure_writes_failed_row(self) -> None:
        gw = self.gw
        gw.fail_with = GatewayError("down")
        with self.assertLogs(LOGGER, "WARNING"):
            pull = pull_day(datetime.date(2026, 10, 9), gw)
        self.assertEqual((pull.status, pull.error), ("FAILED", "down"))
        self.assertIsNotNone(pull.finished_at)
        self.assertEqual(SalesPull.objects.get().status, SalesPull.Status.FAILED)

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
