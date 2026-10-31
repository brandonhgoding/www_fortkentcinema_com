"""Online ticket sales removed (2026-10-31).

The `tickets` app is gone from INSTALLED_APPS, so Django can no longer
migrate it to zero; its tables, content types, permissions and migration
records are dropped here instead. Every step is a no-op on a database that
never had the app (a fresh test database).
"""

from django.db import migrations


def forget_tickets_app(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    # Deleting the content types cascades to their permissions, group and
    # user grants, and admin log entries.
    ContentType.objects.filter(app_label="tickets").delete()
    schema_editor.execute("DELETE FROM django_migrations WHERE app = 'tickets'")


class Migration(migrations.Migration):

    dependencies = [
        ("cinema", "0029_showtime_online_allowance"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # Lines first: they point at orders, and orders at showtimes.
        migrations.RunSQL(
            "DROP TABLE IF EXISTS tickets_ticketline",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS tickets_ticketorder",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(forget_tickets_app, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="showtime",
            name="online_allowance",
        ),
    ]
