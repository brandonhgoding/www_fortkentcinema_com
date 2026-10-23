from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = ("accounts", "0001_initial")
AFTER = ("accounts", "0002_email_login")


def migrate_to(target):
    """Migrate accounts to target and return the app registry at that state."""
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([target])
    return executor.loader.project_state([target]).apps


class EmailLoginMigrationTests(TransactionTestCase):
    def setUp(self):
        migrate_to(BEFORE)

    def tearDown(self):
        # Seeded duplicates or blanks would stop 0002 from applying, and the
        # database must end at the latest state for the tests that follow.
        migrate_to(BEFORE).get_model("accounts", "User").objects.all().delete()
        migrate_to(AFTER)

    def test_normalises_existing_emails(self):
        old = migrate_to(BEFORE).get_model("accounts", "User")
        old.objects.create(username="s", email=" Staff@Example.com ")
        new = migrate_to(AFTER).get_model("accounts", "User")
        self.assertEqual(
            list(new.objects.values_list("email", flat=True)),
            ["staff@example.com"],
        )

    def test_refuses_duplicate_emails_and_changes_nothing(self):
        old = migrate_to(BEFORE).get_model("accounts", "User")
        a = old.objects.create(username="a", email="x@example.com")
        b = old.objects.create(username="b", email="X@example.com")
        with self.assertRaisesMessage(RuntimeError, f"[{a.pk}, {b.pk}]"):
            migrate_to(AFTER)
        self.assertEqual(
            sorted(old.objects.values_list("email", flat=True)),
            ["X@example.com", "x@example.com"],
        )

    def test_refuses_blank_email(self):
        old = migrate_to(BEFORE).get_model("accounts", "User")
        u = old.objects.create(username="a", email="")
        with self.assertRaisesMessage(RuntimeError, f"[{u.pk}]"):
            migrate_to(AFTER)

    def test_reverse_to_0001_restores_username_from_email(self):
        new = migrate_to(AFTER).get_model("accounts", "User")
        new.objects.create(email="staff@example.com")
        old = migrate_to(BEFORE).get_model("accounts", "User")
        self.assertEqual(old.objects.get().username, "staff@example.com")
