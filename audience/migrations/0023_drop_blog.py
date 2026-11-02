"""The blog ("From the Booth") discontinued (2026-11-01).

The `blog` app is gone from INSTALLED_APPS, so Django can no longer migrate
it to zero; its tables, content types, permissions and migration records are
dropped here instead. Every step is a no-op on a database that never had the
app (a fresh test database). Uploaded header images stay in MEDIA_ROOT/blog/
until someone deletes the folder.
"""

from django.db import migrations


def forget_blog_app(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    # Deleting the content types cascades to their permissions, group and
    # user grants, and admin log entries.
    ContentType.objects.filter(app_label="blog").delete()
    schema_editor.execute("DELETE FROM django_migrations WHERE app = 'blog'")


class Migration(migrations.Migration):

    dependencies = [
        ("audience", "0022_remove_membership"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # Posts first: they point at authors and categories.
        migrations.RunSQL(
            "DROP TABLE IF EXISTS blog_blogpost",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS blog_blogauthor",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS blog_blogcategory",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(forget_blog_app, migrations.RunPython.noop),
    ]
