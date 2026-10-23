from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import connection, connections
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase

from accounts.adopt import adopt_auth_user


class AdoptAuthUserTests(TestCase):
    def row(self):
        return MigrationRecorder(connection).migration_qs.filter(
            app="accounts", name="0001_initial"
        )

    def test_records_0001_when_auth_user_exists_and_row_missing(self):
        self.row().delete()
        self.assertTrue(adopt_auth_user(connection))
        self.assertTrue(self.row().exists())

    def test_second_call_changes_nothing(self):
        self.row().delete()
        adopt_auth_user(connection)
        self.assertFalse(adopt_auth_user(connection))
        self.assertEqual(self.row().count(), 1)

    def test_does_nothing_without_auth_user_table(self):
        self.row().delete()
        with mock.patch.object(connection.introspection, "table_names", return_value=[]):
            self.assertFalse(adopt_auth_user(connection))
        self.assertFalse(self.row().exists())

    def test_migrate_prints_adopted_line_only_when_it_acted(self):
        self.row().delete()
        out = StringIO()
        call_command("migrate", plan=True, stdout=out)
        self.assertIn("Adopted the existing auth_user table as accounts.0001_initial.", out.getvalue())
        out = StringIO()
        call_command("migrate", plan=True, stdout=out)
        self.assertNotIn("Adopted", out.getvalue())

    def test_migrate_adopts_on_named_database(self):
        # The row stays: adopt is mocked away, and a missing 0001 under
        # applied dependants would be an inconsistent history.
        with mock.patch("accounts.management.commands.migrate.adopt_auth_user", return_value=False) as adopt:
            call_command("migrate", plan=True, database="default", stdout=StringIO())
        adopt.assert_called_once_with(connections["default"])
