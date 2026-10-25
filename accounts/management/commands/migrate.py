from django.conf import settings
from django.core.management import call_command
from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connections

from accounts.adopt import adopt_auth_user

ADOPTED = "Adopted the existing auth_user table as accounts.0001_initial."
DB_CACHE = "django.core.cache.backends.db.DatabaseCache"
CACHE_TABLE_CREATED = "Created the cache table {}."


class Command(MigrateCommand):
    """migrate, after adopting an existing auth_user table for accounts.User,
    and then creating the default cache's table when that cache is a database
    table (settings.CACHES), so a deploy needs no separate step."""

    def handle(self, *args, **options):
        # --check must change nothing, so it never adopts.
        connection = connections[options["database"]]
        if not options["check_unapplied"] and adopt_auth_user(connection):
            self.stdout.write(ADOPTED)
        result = super().handle(*args, **options)
        if not options["check_unapplied"] and not options["plan"]:
            self.create_cache_table(connection, options["database"])
        return result

    def create_cache_table(self, connection, database):
        default = settings.CACHES.get("default", {})
        if default.get("BACKEND") != DB_CACHE:
            return
        table = default.get("LOCATION", "")
        existed = table in connection.introspection.table_names()
        call_command("createcachetable", database=database, verbosity=0)
        if not existed:
            self.stdout.write(CACHE_TABLE_CREATED.format(table))
