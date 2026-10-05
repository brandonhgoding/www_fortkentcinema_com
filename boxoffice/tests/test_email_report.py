from boxoffice.models import EmailRecipient, EmailReport
from django.db import IntegrityError, transaction
from django.test import TestCase


class EmailReportSeedTests(TestCase):
    def test_both_reports_seeded(self) -> None:
        self.assertEqual(
            set(EmailReport.objects.values_list("kind", flat=True)),
            {"OWNER_SUMMARY", "TICKET_REPORT"},
        )
        self.assertEqual(EmailReport.objects.get(kind="OWNER_SUMMARY").subject,
                         "Daily Sales Summary")
        self.assertTrue(EmailReport.objects.get(kind="TICKET_REPORT").enabled)


class EmailRecipientTests(TestCase):
    def test_to_and_cc_split(self) -> None:
        report = EmailReport.objects.get(kind="OWNER_SUMMARY")
        EmailRecipient.objects.create(report=report, address="owner@example.com")
        EmailRecipient.objects.create(report=report, address="cc@example.com", cc=True)
        self.assertEqual(report.to_addresses(), ["owner@example.com"])
        self.assertEqual(report.cc_addresses(), ["cc@example.com"])

    def test_duplicate_address_per_report_refused(self) -> None:
        report = EmailReport.objects.get(kind="TICKET_REPORT")
        EmailRecipient.objects.create(report=report, address="a@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            EmailRecipient.objects.create(
                report=report, address="a@example.com", cc=True
            )
