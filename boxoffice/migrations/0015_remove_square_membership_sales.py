"""Online membership sales removed (2026-10-31).

Memberships are sold at the box office and entered by staff, so the Square
webhook, the MembershipSale audit rows and the `join` app's website
checkout are gone. `join` is out of INSTALLED_APPS, so Django can no longer
migrate it to zero; its table, content types, permissions and migration
records are dropped here instead, before MembershipSale (the join table
points at it). MembershipSale's own content type goes too, taking the
permissions granted on it. Every join step is a no-op on a database that
never had the app (a fresh test database).
"""

from django.db import migrations


def forget_join_app(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    # Deleting the content types cascades to their permissions, group and
    # user grants, and admin log entries.
    ContentType.objects.filter(app_label="join").delete()
    schema_editor.execute("DELETE FROM django_migrations WHERE app = 'join'")
    ContentType.objects.filter(app_label="boxoffice", model="membershipsale").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("boxoffice", "0014_membershipsale_source"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunSQL(
            "DROP TABLE IF EXISTS join_membershiporder",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(forget_join_app, migrations.RunPython.noop),
        migrations.DeleteModel(
            name="MembershipSale",
        ),
    ]
