from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connections

from accounts.adopt import adopt_auth_user

ADOPTED = "Adopted the existing auth_user table as accounts.0001_initial."


class Command(MigrateCommand):
    """migrate, after adopting an existing auth_user table for accounts.User."""

    def handle(self, *args, **options):
        # --check must change nothing, so it never adopts.
        if not options["check_unapplied"] and adopt_auth_user(connections[options["database"]]):
            self.stdout.write(ADOPTED)
        return super().handle(*args, **options)
