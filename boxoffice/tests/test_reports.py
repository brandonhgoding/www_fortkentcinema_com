import datetime
from zoneinfo import ZoneInfo

from boxoffice.models import (
    EmailRecipient, EmailReport, SaleLine, SalesPull, SquareItem, SquareVariation,
)
from boxoffice.reports import (
    DaySales, ItemTotal, owner_summary, pull_status, render_report,
    sales_panel, send_reports, ticket_report, tier_totals,
)
from boxoffice.tests.test_pull import make_eng
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from tickets.tests.factories import make_showtime

DAY = datetime.date(2026, 10, 9)
LOGGER = "boxoffice.reports"
_seq = iter(range(1, 10_000))


def at_eastern(day: datetime.date, hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime.combine(
        day, datetime.time(hour, minute), tzinfo=ZoneInfo("America/New_York"))


def make_line(item_name, gross_cents, quantity=1, **over) -> SaleLine:
    n = next(_seq)
    fields = dict(
        order_id=f"O{n}", line_uid=f"L{n}", business_date=DAY,
        closed_at=timezone.now(), item_name=item_name, quantity=quantity,
        gross_cents=gross_cents,
    )
    fields.update(over)
    # As the pull stores it: a register sale's show day is its sale day.
    fields.setdefault("show_date", fields["business_date"])
    return SaleLine.objects.create(**fields)


class AggregationTests(TestCase):
    def test_owner_summary_groups_every_line(self) -> None:
        make_line("Dune", 800)
        make_line("Dune", 800)
        make_line("Popcorn", 500, quantity=2)
        make_line("Other day", 900, business_date=datetime.date(2026, 10, 8))
        self.assertEqual(
            owner_summary(DAY),
            [ItemTotal("Dune", 2, 1600), ItemTotal("Popcorn", 2, 500)],
        )

    def test_refunded_lines_are_left_out_of_the_summaries(self) -> None:
        # A refunded ticket stays on its Square order; the ledger carries
        # what was given back so the reports count only what was kept.
        eng = make_eng()
        make_line("Dune", 1600, quantity=2, engagement=eng)
        make_line("Dune", 800, engagement=eng, refunded_quantity=1,
                  refunded_cents=800)
        make_line("Gone", 800, engagement=eng, refunded_quantity=1,
                  refunded_cents=800)
        make_line("Popcorn", 500, quantity=2)
        with override_settings(SQUARE_TICKET_CATEGORY_ID="CAT-TICKETS"):
            self.assertEqual(ticket_report(DAY), [ItemTotal("Dune", 2, 1600)])
        self.assertEqual(owner_summary(DAY),
                         [ItemTotal("Dune", 2, 1600), ItemTotal("Popcorn", 2, 500)])

    def test_ties_sort_by_name(self) -> None:
        make_line("B", 500)
        make_line("A", 500)
        self.assertEqual([r.name for r in owner_summary(DAY)], ["A", "B"])

    def test_ticket_report_excludes_flagged_run_and_concessions(self) -> None:
        a = make_eng()
        b = make_eng(in_ticket_report=False)
        make_line("A", 800, engagement=a)
        make_line("B", 800, engagement=b)
        make_line("Popcorn", 500, category_id="CAT-FOOD")
        with override_settings(SQUARE_TICKET_CATEGORY_ID="CAT-TICKETS"):
            self.assertEqual([r.name for r in ticket_report(DAY)], ["A"])

    def test_ticket_report_includes_unattributed_ticket_category_lines(self) -> None:
        make_line("Hand-made Dune", 800, category_id="CAT-TICKETS")
        make_line("Popcorn", 500, category_id="CAT-FOOD")
        with override_settings(SQUARE_TICKET_CATEGORY_ID="CAT-TICKETS"):
            self.assertEqual(ticket_report(DAY), [ItemTotal("Hand-made Dune", 1, 800)])

    def test_blank_ticket_category_setting_matches_nothing(self) -> None:
        make_line("Uncategorised", 800, category_id="")
        with override_settings(SQUARE_TICKET_CATEGORY_ID=""):
            self.assertEqual(ticket_report(DAY), [])

    def test_ticket_report_dates_online_sales_by_show_day(self) -> None:
        # Sold on DAY for a show two days later: the owner summary counts it
        # on DAY, the ticket report on the show day.
        show_day = DAY + datetime.timedelta(days=2)
        showtime = make_showtime(starts_at=at_eastern(show_day, 19, 0))
        make_line("Dune", 800, engagement=showtime.engagement, showtime=showtime,
                  show_date=show_day)
        self.assertEqual(owner_summary(DAY), [ItemTotal("Dune", 1, 800)])
        self.assertEqual(ticket_report(DAY), [])
        self.assertEqual(ticket_report(show_day), [ItemTotal("Dune", 1, 800)])

    def test_tier_totals_date_online_sales_by_show_day(self) -> None:
        show_day = DAY + datetime.timedelta(days=2)
        showtime = make_showtime(starts_at=at_eastern(show_day, 19, 0))
        item = SquareItem.objects.create(engagement=showtime.engagement, name="Dune")
        adult = SquareVariation.objects.create(
            item=item, square_id="V1", sku="s1", tier="adult", name="Adult",
            price_cents=1000, ordinal=0)
        make_line("Dune", 1000, quantity=2, variation=adult,
                  engagement=showtime.engagement, showtime=showtime,
                  show_date=show_day)
        self.assertEqual(tier_totals(DAY)["adult"], 0)
        self.assertEqual(tier_totals(show_day)["adult"], 2)

    def test_a_deleted_showtime_keeps_its_show_day(self) -> None:
        # The stored day is the record; losing the showtime row must not
        # flip the line back to its sale day.
        show_day = DAY + datetime.timedelta(days=2)
        make_line("Dune", 800, engagement=make_eng(), showtime=None,
                  show_date=show_day)
        self.assertEqual(ticket_report(DAY), [])
        self.assertEqual(ticket_report(show_day), [ItemTotal("Dune", 1, 800)])

    def test_tier_totals_cover_the_three_variations(self) -> None:
        eng = make_eng()
        item = SquareItem.objects.create(engagement=eng, name="Dune")
        adult = SquareVariation.objects.create(
            item=item, square_id="V1", sku="s1", tier="adult", name="Adult",
            price_cents=1000, ordinal=0)
        matinee = SquareVariation.objects.create(
            item=item, square_id="V2", sku="s2", tier="matinee", name="Matinee",
            price_cents=800, ordinal=3)
        make_line("Dune", 1000, quantity=2, variation=adult, engagement=eng)
        make_line("Dune", 800, variation=matinee, engagement=eng)
        make_line("Popcorn", 500, quantity=4)
        make_line("Dune", 1000, quantity=3, variation=adult, engagement=eng,
                  refunded_quantity=3, refunded_cents=3000)
        self.assertEqual(
            tier_totals(DAY),
            {"adult": 2, "senior": 0, "child": 0},
        )


class RenderTests(TestCase):
    def test_owner_summary_body_matches_script_shape(self) -> None:
        body = render_report("OWNER_SUMMARY", DAY, [ItemTotal("Dune", 2, 1600)])
        self.assertIn("Dune: 2 sold for $16.00", body)
        self.assertIn("Total: 2 sold for $16.00", body)

    def test_ticket_report_body(self) -> None:
        body = render_report("TICKET_REPORT", DAY, [ItemTotal("Dune", 2, 1600)])
        self.assertIn("🎟 Ticket Sales Summary:", body)
        self.assertIn("Dune: 2 sold, $16.00 revenue", body)
        self.assertIn("Report generated for October 9, 2026", body)

    def test_quiet_day_bodies(self) -> None:
        self.assertIn("No sales were recorded for October 9, 2026",
                      render_report("OWNER_SUMMARY", DAY, []))
        self.assertIn("No ticket sales were recorded for October 9, 2026",
                      render_report("TICKET_REPORT", DAY, []))


class SendReportsTests(TestCase):
    def setUp(self) -> None:
        self.owner = EmailReport.objects.get(kind=EmailReport.Kind.OWNER_SUMMARY)
        self.tickets = EmailReport.objects.get(kind=EmailReport.Kind.TICKET_REPORT)
        EmailRecipient.objects.create(report=self.owner, address="owner@example.com")
        EmailRecipient.objects.create(
            report=self.owner, address="cc@example.com", cc=True)
        EmailRecipient.objects.create(report=self.tickets, address="booker@example.com")
        self.pull = SalesPull.objects.create(business_date=DAY, status="OK")
        make_line("Popcorn", 500, category_id="CAT-FOOD")

    def test_sends_both_and_records(self) -> None:
        send_reports(DAY, self.pull)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["owner@example.com"])
        self.assertEqual(mail.outbox[0].cc, ["cc@example.com"])
        self.assertIn("Popcorn: 1 sold for $5.00", mail.outbox[0].body)
        self.assertEqual(mail.outbox[1].to, ["booker@example.com"])
        self.pull.refresh_from_db()
        self.assertTrue(self.pull.owner_email_sent and self.pull.report_email_sent)

    def test_disabled_report_skipped(self) -> None:
        self.tickets.enabled = False
        self.tickets.save()
        with self.assertLogs(LOGGER, "INFO"):
            send_reports(DAY, self.pull)
        self.assertEqual([m.subject for m in mail.outbox], ["Daily Sales Summary"])
        self.pull.refresh_from_db()
        self.assertTrue(self.pull.owner_email_sent)
        self.assertFalse(self.pull.report_email_sent)

    def test_report_with_only_cc_is_skipped(self) -> None:
        EmailRecipient.objects.filter(report__kind="TICKET_REPORT").update(cc=True)
        with self.assertLogs(LOGGER, "INFO"):
            send_reports(DAY, self.pull)
        self.assertEqual([m.subject for m in mail.outbox], ["Daily Sales Summary"])
        self.pull.refresh_from_db()
        self.assertFalse(self.pull.report_email_sent)

    def test_dry_run_sends_nothing(self) -> None:
        with self.assertLogs(LOGGER, "INFO") as logs:
            send_reports(DAY, self.pull, dry_run=True)
        self.assertEqual(mail.outbox, [])
        text = "\n".join(logs.output)
        self.assertIn("Daily Sales Summary", text)
        self.assertIn("owner@example.com", text)
        self.assertIn("Popcorn: 1 sold for $5.00", text)
        self.pull.refresh_from_db()
        self.assertFalse(self.pull.owner_email_sent or self.pull.report_email_sent)

    def test_subject_comes_from_admin_row(self) -> None:
        self.owner.subject = "Flash gross"
        self.owner.save()
        send_reports(DAY, self.pull)
        self.assertEqual(mail.outbox[0].subject, "Flash gross")


class SalesPanelTests(TestCase):
    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_none_when_disabled(self) -> None:
        self.assertIsNone(sales_panel(datetime.date(2026, 10, 9)))

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="",
                       SQUARE_TICKET_CATEGORY_ID="C")
    def test_none_when_misconfigured(self) -> None:
        self.assertIsNone(sales_panel(datetime.date(2026, 10, 9)))

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C")
    def test_yesterday_and_same_weekday_last_week(self) -> None:
        eng = make_eng()
        oct8 = datetime.date(2026, 10, 8)
        oct1 = datetime.date(2026, 10, 1)
        make_line("Dune", 1600, quantity=2, engagement=eng, business_date=oct8)
        make_line("Popcorn", 500, business_date=oct8)
        make_line("Dune", 800, engagement=eng, business_date=oct1)
        make_line("Dune", 800, engagement=eng, business_date=oct8,
                  refunded_quantity=1, refunded_cents=800)
        make_line("Soda", 300, business_date=oct8, refunded_quantity=1,
                  refunded_cents=300)
        panel = sales_panel(datetime.date(2026, 10, 9))
        self.assertEqual(panel["yesterday"], DaySales(2100, 2, 500))
        self.assertEqual(panel["last_week"], DaySales(800, 1, 0))
        self.assertFalse(panel["has_pulls"])
        self.assertEqual(panel["yesterday_label"], "Yesterday")
        self.assertEqual(panel["last_week_label"], "Last Thursday")
        self.assertEqual(panel["yesterday"].gross_dollars, "21.00")
        self.assertEqual(panel["yesterday"].concessions_dollars, "5.00")

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C")
    def test_zeros_and_has_pulls(self) -> None:
        SalesPull.objects.create(
            business_date=datetime.date(2026, 10, 8), status=SalesPull.Status.OK)
        panel = sales_panel(datetime.date(2026, 10, 9))
        self.assertEqual(panel["yesterday"], DaySales(0, 0, 0))
        self.assertTrue(panel["has_pulls"])


class PullStatusTests(TestCase):
    def test_missing_failed_ok(self) -> None:
        day = datetime.date(2026, 10, 8)
        self.assertEqual(pull_status(day), "MISSING")
        earlier = timezone.now() - datetime.timedelta(hours=2)
        SalesPull.objects.create(
            business_date=day, status=SalesPull.Status.FAILED, started_at=earlier)
        self.assertEqual(pull_status(day), "FAILED")
        SalesPull.objects.create(business_date=day, status=SalesPull.Status.OK)
        self.assertEqual(pull_status(day), "OK")

    def test_ok_pull_that_missed_online_orders_is_incomplete(self) -> None:
        day = datetime.date(2026, 10, 8)
        SalesPull.objects.create(business_date=day, status=SalesPull.Status.OK,
                                 missing_online=2)
        self.assertEqual(pull_status(day), "INCOMPLETE")

    def test_pull_that_never_finished_is_failed(self) -> None:
        day = datetime.date(2026, 10, 8)
        SalesPull.objects.create(business_date=day, status=SalesPull.Status.FAILED,
                                 error="Pull did not finish")
        self.assertEqual(pull_status(day), "FAILED")
