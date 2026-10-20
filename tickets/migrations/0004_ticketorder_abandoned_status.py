# A checkout Square never started is ABANDONED, not "Needs attention": there
# is nothing for staff to do about it. Existing FAILED orders without a
# payment are exactly those, so they move too.

from django.db import migrations, models


def abandon_never_started(apps, schema_editor):
    TicketOrder = apps.get_model("tickets", "TicketOrder")
    TicketOrder.objects.filter(status="FAILED", square_payment_id="").update(
        status="ABANDONED"
    )


def fail_never_started(apps, schema_editor):
    TicketOrder = apps.get_model("tickets", "TicketOrder")
    TicketOrder.objects.filter(status="ABANDONED").update(status="FAILED")


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0003_ticketorder_split_name_square_customer"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ticketorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("PAID", "Paid"),
                    ("EXPIRED", "Expired"),
                    ("REFUNDED", "Refunded"),
                    ("FAILED", "Needs attention"),
                    ("ABANDONED", "Never started"),
                ],
                default="PENDING",
                max_length=9,
            ),
        ),
        migrations.RunPython(abandon_never_started, fail_never_started),
    ]
