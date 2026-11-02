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

The same old generation was a Wagtail site, and its tables (at least
wagtailcore_referenceindex) still point at the blog's content type. Every
grant of a blog permission is removed first, unconditionally. Removing the
content types themselves, with their permissions and admin log entries, is
then tried in a savepoint with constraints checked immediately: if a legacy
table still refers to them, those rows stay, unused and granted to nobody,
rather than failing the deploy at COMMIT.
"""

from django.db import IntegrityError, migrations, transaction


# Posts first: they point at authors and categories.
BLOG_TABLES = ("blog_blogpost", "blog_blogauthor", "blog_blogcategory")


def drop_blog_tables(apps, schema_editor):
    cascade = " CASCADE" if schema_editor.connection.vendor == "postgresql" else ""
    for table in BLOG_TABLES:
        schema_editor.execute(f"DROP TABLE IF EXISTS {table}{cascade}")


def forget_blog_app(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("accounts", "User")
    connection = schema_editor.connection
    postgres = connection.vendor == "postgresql"

    blog_types = ContentType.objects.filter(app_label="blog")
    blog_perms = Permission.objects.filter(content_type__in=blog_types)
    Permission.group_set.through.objects.filter(permission__in=blog_perms).delete()
    User.user_permissions.through.objects.filter(permission__in=blog_perms).delete()

    try:
        with transaction.atomic(using=connection.alias):
            if postgres:
                # Django's foreign keys are deferred to COMMIT, where a
                # failure can no longer be caught. Check them now instead.
                schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            # Cascades to the permissions and admin log entries.
            blog_types.delete()
    except IntegrityError:
        pass  # a legacy table still points at them; see the docstring
    finally:
        if postgres:
            schema_editor.execute("SET CONSTRAINTS ALL DEFERRED")

    schema_editor.execute("DELETE FROM django_migrations WHERE app = 'blog'")


class Migration(migrations.Migration):

    dependencies = [
        ("audience", "0022_remove_membership"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("accounts", "0005_drop_email_verified_at"),
    ]

    operations = [
        migrations.RunPython(drop_blog_tables, migrations.RunPython.noop),
        migrations.RunPython(forget_blog_app, migrations.RunPython.noop),
    ]
