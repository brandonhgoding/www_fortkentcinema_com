import datetime
from io import StringIO
from unittest import mock

from boxoffice.gateway import GatewayError, RemoteItem
from boxoffice.models import EmailRecipient, EmailReport, SaleLine, SalesPull
from boxoffice.tests.fakes import FakeGateway
from boxoffice.tests.test_pull import at_eastern, line, order
from boxoffice.sync import push
from boxoffice.tests.test_sync import make_eng
from cinema.models import Film
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

COMMAND_GATEWAY = "boxoffice.management.commands.sync_square_catalog.get_gateway"
PULL_GATEWAY = "boxoffice.management.commands.pull_square_sales.get_gateway"
PULL_SEND = "boxoffice.management.commands.pull_square_sales.send_reports"


class SyncSquareCatalogCommandTests(TestCase):
    def test_disabled_without_token(self) -> None:
        out = StringIO()
        with override_settings(SQUARE_ACCESS_TOKEN=""):
            call_command("sync_square_catalog", stdout=out)
        self.assertIn("disabled (no SQUARE_ACCESS_TOKEN)", out.getvalue())

    def test_disabled_names_the_blank_id(self) -> None:
        out = StringIO()
        with override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="",
                               SQUARE_TICKET_CATEGORY_ID="C"), \
                self.assertLogs("boxoffice.gateway", "ERROR"):
            call_command("sync_square_catalog", stdout=out)
        self.assertIn("disabled (SQUARE_LOCATION_ID is blank)", out.getvalue())

    def test_dry_run_prints_plan(self) -> None:
        make_eng()
        out = StringIO()
        with mock.patch(COMMAND_GATEWAY, return_value=FakeGateway()):
            call_command("sync_square_catalog", "--dry-run", stdout=out)
        self.assertIn("Would push 1", out.getvalue())

    def test_dry_run_counts_posters_to_attach(self) -> None:
        eng = make_eng()
        Film.objects.filter(pk=eng.primary_film.pk).update(
            poster_url="https://image.tmdb.org/t/p/w500/dune.jpg")
        gw = FakeGateway()
        push(eng, gw)
        out = StringIO()
        with mock.patch(COMMAND_GATEWAY, return_value=gw):
            call_command("sync_square_catalog", "--dry-run", stdout=out)
        self.assertIn("Would attach 1 poster", out.getvalue())

    def test_image_skips_are_printed_but_not_errors(self) -> None:
        eng = make_eng()
        Film.objects.filter(pk=eng.primary_film.pk).update(
            poster_url="https://image.tmdb.org/t/p/w500/dune.jpg")
        gw = FakeGateway()
        push(eng, gw)
        out = StringIO()
        with mock.patch(COMMAND_GATEWAY, return_value=gw), \
                mock.patch("boxoffice.sync.fetch_poster", return_value=None):
            call_command("sync_square_catalog", stdout=out)  # no CommandError
        self.assertIn("Posters skipped:", out.getvalue())
        self.assertIn("Attached 0 posters", out.getvalue())

    def test_real_run_prints_counts(self) -> None:
        make_eng()
        out = StringIO()
        with mock.patch(COMMAND_GATEWAY, return_value=FakeGateway()):
            call_command("sync_square_catalog", stdout=out)
        self.assertIn("Pushed 1", out.getvalue())
        self.assertIn("Deleted 0", out.getvalue())

    def test_errors_print_and_raise(self) -> None:
        gw = FakeGateway()
        gw.items["orphan"] = RemoteItem("orphan", 1, "Old", {"fkc-eng-9-adult": "v"})
        out = StringIO()
        with mock.patch(COMMAND_GATEWAY, return_value=gw):
            with self.assertRaises(CommandError):
                call_command("sync_square_catalog", stdout=out)
        self.assertIn("ERROR: Django-made item without a link row: orphan",
                      out.getvalue())


class PullSquareSalesCommandTests(TestCase):
    def setUp(self) -> None:
        for kind in ("OWNER_SUMMARY", "TICKET_REPORT"):
            EmailRecipient.objects.create(
                report=EmailReport.objects.get(kind=kind), address="owner@example.com")
        self.gw = FakeGateway()
        self.gw.orders = [
            order("O7", at_eastern(2026, 10, 7, 19, 0),
                  line("L7", "Popcorn", "", "VPOP", 1, 500)),
            order("O9", at_eastern(2026, 10, 9, 19, 0),
                  line("L9a", "Popcorn", "", "VPOP", 2, 1000),
                  line("L9b", "Soda", "", "VSODA", 1, 300)),
        ]

    def run_command(self, *args, gateway="default"):
        gw = self.gw if gateway == "default" else gateway
        out = StringIO()
        with mock.patch(PULL_GATEWAY, return_value=gw):
            call_command("pull_square_sales", *args, stdout=out)
        return out.getvalue()

    def test_pulls_three_days_and_emails_target_only(self) -> None:
        out = self.run_command("--date", "2026-10-09")
        self.assertEqual(
            set(SalesPull.objects.values_list("business_date", flat=True)),
            {datetime.date(2026, 10, 7), datetime.date(2026, 10, 8),
             datetime.date(2026, 10, 9)})
        self.assertEqual(SaleLine.objects.count(), 3)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("October 9, 2026", mail.outbox[1].body)
        self.assertIn("2026-10-09: OK, 1 orders, 2 lines", out)

    def test_days_option_limits_lookback(self) -> None:
        self.run_command("--date", "2026-10-09", "--days", "1")
        self.assertEqual(SalesPull.objects.count(), 1)

    def test_days_must_be_positive(self) -> None:
        with self.assertRaises(CommandError):
            self.run_command("--date", "2026-10-09", "--days", "0")

    def test_no_email_flag(self) -> None:
        self.run_command("--date", "2026-10-09", "--no-email")
        self.assertEqual(SalesPull.objects.count(), 3)
        self.assertEqual(mail.outbox, [])

    def test_dry_run_writes_nothing(self) -> None:
        out = self.run_command("--date", "2026-10-09", "--dry-run")
        self.assertIn("Would store 2 lines from 1 orders for 2026-10-09", out)
        self.assertIn("Would store 1 lines from 1 orders for 2026-10-07", out)
        self.assertEqual(SaleLine.objects.count(), 0)
        self.assertEqual(SalesPull.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_dry_run_gateway_error_exits_nonzero(self) -> None:
        out = StringIO()
        gw = FakeGateway(fail_with=GatewayError("down"))
        with mock.patch(PULL_GATEWAY, return_value=gw):
            with self.assertRaises(CommandError):
                call_command("pull_square_sales", "--dry-run", stdout=out)
        self.assertIn("ERROR: down", out.getvalue())

    def test_failed_pull_exits_nonzero(self) -> None:
        gw = FakeGateway(fail_with=GatewayError("down"))
        out = StringIO()
        with mock.patch(PULL_GATEWAY, return_value=gw):
            with self.assertLogs("boxoffice.pull", level="WARNING"), \
                    self.assertRaises(CommandError):
                call_command("pull_square_sales", "--date", "2026-10-09", stdout=out)
        pulls = SalesPull.objects.all()
        self.assertEqual(pulls.count(), 3)
        self.assertTrue(all(p.status == SalesPull.Status.FAILED for p in pulls))
        self.assertIn("FAILED", out.getvalue())
        self.assertEqual(mail.outbox, [])

    def test_email_failure_exits_nonzero_but_pull_stays_ok(self) -> None:
        with mock.patch(PULL_SEND, side_effect=RuntimeError("smtp down")):
            with self.assertLogs("boxoffice", level="ERROR"):
                with self.assertRaises(CommandError):
                    self.run_command("--date", "2026-10-09")
        pull = SalesPull.objects.get(business_date=datetime.date(2026, 10, 9))
        self.assertTrue(pull.error.startswith("Email failed"))
        self.assertEqual(pull.status, "OK")

    def test_disabled_without_token(self) -> None:
        for args in ((), ("--dry-run",)):
            out = self.run_command(*args, gateway=None)
            self.assertIn("disabled (no SQUARE_ACCESS_TOKEN)", out)
        self.assertEqual(SalesPull.objects.count(), 0)

    def test_disabled_names_the_blank_id(self) -> None:
        out = StringIO()
        with override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                               SQUARE_TICKET_CATEGORY_ID=""), \
                self.assertLogs("boxoffice.gateway", "ERROR"):
            call_command("pull_square_sales", stdout=out)
        self.assertIn("disabled (SQUARE_TICKET_CATEGORY_ID is blank)", out.getvalue())
        self.assertEqual(SalesPull.objects.count(), 0)
