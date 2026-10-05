"""Seed the two nightly reports so recipients can be added in the admin."""

from django.db import migrations

REPORTS = {
    "OWNER_SUMMARY": "Daily Sales Summary",
    "TICKET_REPORT": "Ticket Sales Report",
}


def seed(apps, schema_editor):
    EmailReport = apps.get_model("boxoffice", "EmailReport")
    for kind, subject in REPORTS.items():
        EmailReport.objects.get_or_create(
            kind=kind, defaults={"subject": subject}
        )


def unseed(apps, schema_editor):
    EmailReport = apps.get_model("boxoffice", "EmailReport")
    EmailReport.objects.filter(kind__in=REPORTS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("boxoffice", "0002_emailreport_emailrecipient"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
