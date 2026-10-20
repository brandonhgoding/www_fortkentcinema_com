from django.db import migrations, models

from tickets.models import split_name


def split_names(apps, schema_editor):
    TicketOrder = apps.get_model("tickets", "TicketOrder")
    for order in TicketOrder.objects.all().only("pk", "name"):
        order.first_name, order.last_name = split_name(order.name)
        order.save(update_fields=["first_name", "last_name"])


def join_names(apps, schema_editor):
    TicketOrder = apps.get_model("tickets", "TicketOrder")
    for order in TicketOrder.objects.all().only("pk", "first_name", "last_name"):
        order.name = f"{order.first_name} {order.last_name}".strip()
        order.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0002_ticketline_tickets_line_quantity_at_least_one"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticketorder",
            name="first_name",
            field=models.CharField(default="", max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="ticketorder",
            name="last_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="ticketorder",
            name="square_customer_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.RunPython(split_names, join_names),
        migrations.RemoveField(model_name="ticketorder", name="name"),
    ]
