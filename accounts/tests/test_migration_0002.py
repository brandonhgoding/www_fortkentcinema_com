from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = ("accounts", "0001_initial")
AFTER = ("accounts", "0002_email_login")


LATEST = ("accounts", "0004_user_email_verified_at")


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
        migrate_to(LATEST)

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

    def test_reverse_fits_overlong_email_into_username(self):
        new = migrate_to(AFTER).get_model("accounts", "User")
        long_email = "a" * 160 + "@example.com"
        user = new.objects.create(email=long_email)
        short = new.objects.create(email="short@example.com")
        old = migrate_to(BEFORE).get_model("accounts", "User")
        self.assertEqual(old.objects.get(pk=user.pk).username, f"user{user.pk}")
        self.assertEqual(old.objects.get(pk=short.pk).username, "short@example.com")


class MoveUserContentTypeTests(TransactionTestCase):
    def setUp(self):
        self.apps = migrate_to(BEFORE)

    def tearDown(self):
        migrate_to(LATEST)

    def _m(self, app, name):
        return self.apps.get_model(app, name)

    def _auth_only(self):
        """Simulate production: the user content type still lives in auth."""
        CT = self._m("contenttypes", "ContentType")
        CT.objects.filter(app_label="auth", model="user").delete()
        ct = CT.objects.get(app_label="accounts", model="user")
        ct.app_label = "auth"
        ct.save()
        return ct

    def _assert_settled(self):
        cts = ContentType.objects.filter(model="user")
        self.assertEqual(
            list(cts.values_list("app_label", flat=True)), ["accounts"]
        )
        self.assertEqual(Permission.objects.filter(content_type=cts[0]).count(), 4)

    def test_renames_auth_user_content_type(self):
        ct = self._auth_only()
        migrate_to(LATEST)
        moved = ContentType.objects.get(app_label="accounts", model="user")
        self.assertEqual(moved.pk, ct.pk)
        self.assertFalse(ContentType.objects.filter(app_label="auth", model="user"))
        self._assert_settled()

    def test_group_permission_survives_content_type_move(self):
        ct = self._auth_only()
        perm = self._m("auth", "Permission").objects.get(
            content_type=ct, codename="change_user"
        )
        group = self._m("auth", "Group").objects.create(name="staff-editors")
        group.permissions.add(perm)
        old = self.apps.get_model("accounts", "User").objects.create(
            username="s", email="s@example.com"
        )
        old.groups.add(group)
        migrate_to(LATEST)
        user = get_user_model().objects.get(pk=old.pk)
        self.assertTrue(user.has_perm("accounts.change_user"))

    def test_both_content_types_merge_into_accounts(self):
        CT = self._m("contenttypes", "ContentType")
        Perm = self._m("auth", "Permission")
        new_ct = CT.objects.get(app_label="accounts", model="user")
        old_ct = CT.objects.create(app_label="auth", model="user")
        old_change = Perm.objects.create(
            content_type=old_ct, codename="change_user", name="Can change user"
        )
        extra = Perm.objects.create(
            content_type=old_ct, codename="legacy_user", name="Legacy"
        )
        group = self._m("auth", "Group").objects.create(name="staff-editors")
        group.permissions.add(old_change, extra)
        holder = self.apps.get_model("accounts", "User").objects.create(
            username="h", email="h@example.com"
        )
        holder.user_permissions.add(old_change)
        entry = LogEntry.objects.create(
            user_id=holder.pk,
            content_type_id=old_ct.pk,
            object_id="1",
            object_repr="x",
            action_flag=2,
        )
        migrate_to(LATEST)
        self.assertFalse(ContentType.objects.filter(app_label="auth", model="user"))
        self._assert_settled_with_extra()
        group = Group.objects.get(name="staff-editors")
        codenames = set(group.permissions.values_list("codename", flat=True))
        self.assertEqual(codenames, {"change_user", "legacy_user"})
        self.assertTrue(
            group.permissions.filter(
                content_type_id=new_ct.pk, codename="change_user"
            ).exists()
        )
        user = get_user_model().objects.get(pk=holder.pk)
        held = user.user_permissions.filter(content_type_id=new_ct.pk)
        self.assertTrue(held.exists())
        entry.refresh_from_db()
        self.assertEqual(entry.content_type_id, new_ct.pk)

    def _assert_settled_with_extra(self):
        cts = ContentType.objects.filter(model="user")
        self.assertEqual(
            list(cts.values_list("app_label", flat=True)), ["accounts"]
        )
        self.assertEqual(Permission.objects.filter(content_type=cts[0]).count(), 5)
