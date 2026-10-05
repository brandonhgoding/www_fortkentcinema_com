from io import StringIO
from unittest import mock

from boxoffice.gateway import RemoteItem
from boxoffice.tests.fakes import FakeGateway
from boxoffice.tests.test_sync import make_eng
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

COMMAND_GATEWAY = "boxoffice.management.commands.sync_square_catalog.get_gateway"


class SyncSquareCatalogCommandTests(TestCase):
    def test_disabled_without_token(self) -> None:
        out = StringIO()
        with override_settings(SQUARE_ACCESS_TOKEN=""):
            call_command("sync_square_catalog", stdout=out)
        self.assertIn("disabled", out.getvalue())

    def test_dry_run_prints_plan(self) -> None:
        make_eng()
        out = StringIO()
        with mock.patch(COMMAND_GATEWAY, return_value=FakeGateway()):
            call_command("sync_square_catalog", "--dry-run", stdout=out)
        self.assertIn("Would push 1", out.getvalue())

    def test_real_run_prints_counts(self) -> None:
        make_eng()
        out = StringIO()
        with mock.patch(COMMAND_GATEWAY, return_value=FakeGateway()):
            call_command("sync_square_catalog", stdout=out)
        self.assertIn("Pushed 1", out.getvalue())
        self.assertIn("Deleted 0", out.getvalue())

    def test_errors_print_and_raise(self) -> None:
        gw = FakeGateway()
        gw.items["orphan"] = RemoteItem("orphan", 1, "Old", {"fkc-eng-9-adult": "v"})
        out = StringIO()
        with mock.patch(COMMAND_GATEWAY, return_value=gw):
            with self.assertRaises(CommandError):
                call_command("sync_square_catalog", stdout=out)
        self.assertIn("ERROR: Django-made item without a link row: orphan",
                      out.getvalue())
