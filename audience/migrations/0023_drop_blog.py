"""The blog ("From the Booth") discontinued (2026-11-01).

The `blog` app is gone from INSTALLED_APPS, so Django can no longer migrate
it to zero; its tables, content types, permissions and migration records are
dropped here instead. Every step is a no-op on a database that never had the
app (a fresh test database). Uploaded header images stay in MEDIA_ROOT/blog/
until someone deletes the folder.

Production also holds tables from an older generation of the site that no
app here owns (website_blogpage, with a foreign key to blog_blogauthor). On
Postgres the drops CASCADE, which removes those foreign-key constraints and
nothing else: the old tables and their rows stay. SQLite has no CASCADE and
no such tables.
"""

from django.db import migrations


# Posts first: they point at authors and categories.
BLOG_TABLES = ("blog_blogpost", "blog_blogauthor", "blog_blogcategory")


def drop_blog_tables(apps, schema_editor):
    cascade = " CASCADE" if schema_editor.connection.vendor == "postgresql" else ""
    for table in BLOG_TABLES:
        schema_editor.execute(f"DROP TABLE IF EXISTS {table}{cascade}")


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
        migrations.RunPython(drop_blog_tables, migrations.RunPython.noop),
        migrations.RunPython(forget_blog_app, migrations.RunPython.noop),
    ]
