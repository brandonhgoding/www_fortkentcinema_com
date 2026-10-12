import datetime
from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from audience.models import Subscriber, SubscriberStatus

SEED = import_module("audience.migrations.0004_seed_membership_catalogue")
ALLOWANCES = import_module("audience.migrations.0007_seed_free_admission_allowances")


def statuses(sub: Subscriber) -> list[str]:
    return list(sub.changes.order_by("-at", "-pk").values_list("status", flat=True))


class RequestSignupTests(TestCase):
    def test_new_address_is_pending_and_due_an_email(self) -> None:
        sub = Subscriber.objects.request_signup(
            " Fan@Example.com ", "movie_page", "198.51.100.4"
        )
        self.assertEqual(
            (sub.email, sub.status, sub.source, sub.consent_ip),
            (
                "fan@example.com",
                SubscriberStatus.PENDING,
                "movie_page",
                "198.51.100.4",
            ),
        )
        self.assertIsNone(sub.confirmed_at)
        self.assertEqual(sub.changes.get().status, SubscriberStatus.PENDING)

    def test_pending_is_due_again_only_after_an_hour(self) -> None:
        sub = Subscriber.objects.request_signup("fan@example.com", "movie_page")
        Subscriber.objects.filter(pk=sub.pk).update(
            confirmation_sent_at=timezone.now() - datetime.timedelta(minutes=59)
        )
        self.assertIsNone(
            Subscriber.objects.request_signup("FAN@example.com ", "home_showtimes")
        )
        Subscriber.objects.filter(pk=sub.pk).update(
            confirmation_sent_at=timezone.now() - datetime.timedelta(minutes=61)
        )
        again = Subscriber.objects.request_signup("fan@example.com", "home_showtimes")
        self.assertEqual(again.pk, sub.pk)
        self.assertEqual(again.source, "movie_page")  # not overwritten

    def test_pending_never_sent_is_due(self) -> None:
        sub = Subscriber.objects.request_signup("fan@example.com", "movie_page")
        self.assertIsNone(sub.confirmation_sent_at)
        again = Subscriber.objects.request_signup("fan@example.com", "movie_page")
        self.assertEqual(again.pk, sub.pk)

    def test_active_address_is_never_due(self) -> None:
        Subscriber.objects.record("fan@example.com", source="poll_vote")
        self.assertIsNone(
            Subscriber.objects.request_signup("fan@example.com", "movie_page")
        )

    def test_opted_out_address_is_due_but_stays_opted_out(self) -> None:
        sub, _ = Subscriber.objects.record("fan@example.com", source="poll_vote")
        sub.unsubscribe()
        due = Subscriber.objects.request_signup("fan@example.com", "movie_page")
        self.assertEqual(due.status, SubscriberStatus.UNSUBSCRIBED)
        # The hourly limit applies to it too.
        Subscriber.objects.filter(pk=sub.pk).update(confirmation_sent_at=timezone.now())
        self.assertIsNone(
            Subscriber.objects.request_signup("fan@example.com", "movie_page")
        )

    def test_blank_and_overlong_raise(self) -> None:
        for bad in ("", "  ", "a" * 250 + "@x.com"):
            with self.subTest(bad=bad[:10]), self.assertRaises(ValueError):
                Subscriber.objects.request_signup(bad, "movie_page")


class ConfirmTests(TestCase):
    def test_pending_becomes_active_with_a_logged_change(self) -> None:
        sub = Subscriber.objects.request_signup("fan@example.com", "movie_page")
        sub.confirm()
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriberStatus.ACTIVE)
        self.assertIsNotNone(sub.confirmed_at)
        self.assertEqual(
            statuses(sub), [SubscriberStatus.ACTIVE, SubscriberStatus.PENDING]
        )
        latest = sub.changes.order_by("-at", "-pk").first()
        self.assertEqual(latest.at, sub.confirmed_at)

    def test_opted_out_becomes_active_and_keeps_its_history(self) -> None:
        sub, _ = Subscriber.objects.record("fan@example.com", source="poll_vote")
        sub.unsubscribe()
        sub.confirm()
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriberStatus.ACTIVE)
        self.assertIsNone(sub.unsubscribed_at)
        self.assertEqual(
            statuses(sub),
            [
                SubscriberStatus.ACTIVE,
                SubscriberStatus.UNSUBSCRIBED,
                SubscriberStatus.ACTIVE,
            ],
        )

    def test_confirming_an_active_row_changes_nothing(self) -> None:
        sub, _ = Subscriber.objects.record("fan@example.com", source="poll_vote")
        confirmed_at = sub.confirmed_at
        changes = sub.changes.count()
        sub.confirm()
        sub.refresh_from_db()
        self.assertEqual(sub.confirmed_at, confirmed_at)
        self.assertEqual(sub.changes.count(), changes)

    def test_pending_is_not_active(self) -> None:
        Subscriber.objects.request_signup("fan@example.com", "movie_page")
        self.assertFalse(Subscriber.objects.active().exists())


class ConfirmedAtMigrationTests(TransactionTestCase):
    """0015 backfills confirmed_at from consent_at on rows that predate it."""

    migrate_from = [("audience", "0014_membershiptier_square_variation_id_message")]
    migrate_to = [("audience", "0015_subscriber_pending")]

    def setUp(self) -> None:
        self.executor = MigrationExecutor(connection)
        self.addCleanup(self.restore_latest_schema)

    def _fixture_teardown(self) -> None:
        # Reseed what the migrations seeded, as in the term migration test.
        super()._fixture_teardown()
        SEED.seed(self.executor.loader.project_state(self.migrate_to).apps, None)
        ALLOWANCES.set_allowances(
            self.executor.loader.project_state(self.migrate_to).apps, None
        )

    def restore_latest_schema(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate(self, targets):
        self.executor.migrate(targets)
        self.executor.loader.build_graph()
        return self.executor.loader.project_state(targets).apps

    def test_existing_rows_get_confirmed_at_from_consent_at(self) -> None:
        old_apps = self.migrate(self.migrate_from)
        OldSubscriber = old_apps.get_model("audience", "Subscriber")
        pk = OldSubscriber.objects.create(email="old@example.com", source="x").pk
        consent_at = OldSubscriber.objects.get(pk=pk).consent_at

        new_apps = self.migrate(self.migrate_to)
        NewSubscriber = new_apps.get_model("audience", "Subscriber")
        self.assertEqual(NewSubscriber.objects.get(pk=pk).confirmed_at, consent_at)
