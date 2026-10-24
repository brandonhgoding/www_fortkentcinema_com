from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

BEFORE = ("accounts", "0003_drop_personal_names")
AFTER = ("accounts", "0004_user_email_verified_at")


def migrate_to(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([target])
    return executor.loader.project_state([target]).apps


class VerifiedMigrationTests(TransactionTestCase):
    def tearDown(self):
        migrate_to(AFTER)

    def test_migration_marks_existing_users_verified(self):
        old = migrate_to(BEFORE).get_model("accounts", "User")
        old.objects.create(email="a@example.com")
        old.objects.create(email="b@example.com", is_staff=True)
        new = migrate_to(AFTER).get_model("accounts", "User")
        self.assertEqual(new.objects.count(), 2)
        self.assertFalse(new.objects.filter(email_verified_at__isnull=True).exists())


class DeleteUnverifiedAccountsTests(TestCase):
    def make(self, email, days, verified=False, staff=False):
        user = get_user_model().objects.create(
            email=email,
            is_staff=staff,
            email_verified_at=timezone.now() if verified else None,
        )
        get_user_model().objects.filter(pk=user.pk).update(
            date_joined=timezone.now() - timedelta(days=days)
        )
        return user

    def test_deletes_only_old_unverified_members(self):
        self.make("old@example.com", 8)
        self.make("new@example.com", 6)
        self.make("verified@example.com", 30, verified=True)
        self.make("staff@example.com", 30, staff=True)
        out = StringIO()
        call_command("delete_unverified_accounts", stdout=out)
        self.assertEqual(out.getvalue().strip(), "Deleted 1 unverified accounts.")
        self.assertEqual(
            sorted(get_user_model().objects.values_list("email", flat=True)),
            ["new@example.com", "staff@example.com", "verified@example.com"],
        )

    def test_account_that_ever_signed_in_survives(self):
        demoted = self.make("demoted@example.com", 30)
        get_user_model().objects.filter(pk=demoted.pk).update(
            last_login=timezone.now() - timedelta(days=20)
        )
        call_command("delete_unverified_accounts", stdout=StringIO())
        self.assertTrue(get_user_model().objects.filter(pk=demoted.pk).exists())
