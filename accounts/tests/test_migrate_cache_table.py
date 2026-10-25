from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

DB_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


class MigrateCreatesCacheTableTests(TestCase):
    """The default cache is a database table in production; `migrate` makes
    it so a deploy needs no extra step and the table exists before the new
    code serves a request."""

    def run_migrate(self, **options):
        with mock.patch("accounts.management.commands.migrate.call_command") as cc:
            call_command("migrate", stdout=StringIO(), **options)
        return cc

    @override_settings(CACHES=DB_CACHE)
    def test_migrate_creates_the_cache_table(self):
        cc = self.run_migrate()
        cc.assert_called_once()
        self.assertEqual(cc.call_args.args[0], "createcachetable")

    @override_settings(CACHES=DB_CACHE)
    def test_check_and_plan_create_nothing(self):
        for options in ({"check_unapplied": True}, {"plan": True}):
            with self.subTest(options=options):
                try:
                    cc = self.run_migrate(**options)
                except SystemExit:
                    # --check exits non-zero when migrations are pending.
                    continue
                cc.assert_not_called()

    @override_settings(CACHES=LOCMEM)
    def test_in_memory_cache_needs_no_table(self):
        self.run_migrate().assert_not_called()
