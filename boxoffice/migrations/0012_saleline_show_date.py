from zoneinfo import ZoneInfo

from django.db import migrations, models

EASTERN = ZoneInfo("America/New_York")


def backfill(apps, schema_editor):
    SaleLine = apps.get_model("boxoffice", "SaleLine")
    for line in SaleLine.objects.select_related("showtime").iterator():
        if line.showtime is not None:
            line.show_date = line.showtime.starts_at.astimezone(EASTERN).date()
        else:
            line.show_date = line.business_date
        line.save(update_fields=["show_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("boxoffice", "0011_saleline_refunded"),
    ]

    operations = [
        migrations.AddField(
            model_name="saleline",
            name="show_date",
            field=models.DateField(db_index=True, null=True),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="saleline",
            name="show_date",
            field=models.DateField(db_index=True),
        ),
    ]
