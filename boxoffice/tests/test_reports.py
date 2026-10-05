import datetime

from boxoffice.models import (
    EmailRecipient, EmailReport, SaleLine, SalesPull, SquareItem, SquareVariation,
)
from boxoffice.reports import (
    ItemTotal, owner_summary, render_report, send_reports, ticket_report,
    tier_totals,
)
from boxoffice.tests.test_pull import make_eng
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

DAY = datetime.date(2026, 10, 9)
LOGGER = "boxoffice.reports"
_seq = iter(range(1, 10_000))


def make_line(item_name, gross_cents, quantity=1, **over) -> SaleLine:
    n = next(_seq)
    fields = dict(
        order_id=f"O{n}", line_uid=f"L{n}", business_date=DAY,
        closed_at=timezone.now(), item_name=item_name, quantity=quantity,
        gross_cents=gross_cents,
    )
    fields.update(over)
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

    def test_tier_totals_cover_all_five(self) -> None:
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
        self.assertEqual(
            tier_totals(DAY),
            {"adult": 2, "senior": 0, "child": 0, "matinee": 1, "member": 0},
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
