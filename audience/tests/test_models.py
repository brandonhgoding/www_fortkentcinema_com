import datetime
from typing import Any
from unittest import mock

from django.db.models import QuerySet
from django.test import TestCase
from django.utils import timezone

from audience.models import Subscriber, SubscriberStatus


class SubscriberRecordTests(TestCase):
    def test_record_creates_active_subscriber(self) -> None:
        sub, created = Subscriber.objects.record(
            "Someone@Example.COM", source="poll_vote", ip="10.0.0.1"
        )
        self.assertTrue(created)
        self.assertEqual(sub.email, "someone@example.com")
        self.assertEqual(sub.status, SubscriberStatus.ACTIVE)
        self.assertEqual(sub.source, "poll_vote")
        self.assertEqual(sub.consent_ip, "10.0.0.1")
        self.assertIsNotNone(sub.consent_at)
        self.assertIsNotNone(sub.unsubscribe_token)

    def test_record_is_idempotent(self) -> None:
        first, created_first = Subscriber.objects.record(
            "a@example.com", source="poll_vote"
        )
        second, created_second = Subscriber.objects.record(
            "  A@Example.com ", source="poll_vote"
        )
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Subscriber.objects.count(), 1)

    def test_record_never_resurrects_an_unsubscribed_address(self) -> None:
        sub, _ = Subscriber.objects.record("gone@example.com", source="poll_vote")
        sub.unsubscribe()

        again, created = Subscriber.objects.record(
            "gone@example.com", source="poll_vote"
        )

        self.assertFalse(created)
        self.assertEqual(again.pk, sub.pk)
        self.assertEqual(again.status, SubscriberStatus.UNSUBSCRIBED)
        self.assertIsNotNone(again.unsubscribed_at)

    def test_record_rejects_blank_email(self) -> None:
        with self.assertRaises(ValueError):
            Subscriber.objects.record("   ", source="poll_vote")

    def test_record_survives_a_concurrent_signup_for_the_same_address(self) -> None:
        """Two simultaneous POSTs both see "no such address", both insert.

        Simulated by committing the winner's row first and making this
        call's existence lookup miss it once, as it would have a moment
        earlier. The loser must get the winner's row back, not an
        IntegrityError (which the vote page turned into a 500).
        """
        winner, _ = Subscriber.objects.record("race@example.com", source="other")
        real_get, real_first = QuerySet.get, QuerySet.first
        missed: list[str] = []

        def get(qs: QuerySet, *args: Any, **kwargs: Any) -> Any:
            if qs.model is Subscriber and not missed:
                missed.append("get")
                raise Subscriber.DoesNotExist
            return real_get(qs, *args, **kwargs)

        def first(qs: QuerySet) -> Any:
            if qs.model is Subscriber and not missed:
                missed.append("first")
                return None
            return real_first(qs)

        with (
            mock.patch.object(QuerySet, "get", get),
            mock.patch.object(QuerySet, "first", first),
        ):
            sub, created = Subscriber.objects.record(
                "Race@Example.com", source="poll_vote"
            )

        self.assertTrue(missed)
        self.assertFalse(created)
        self.assertEqual(sub.pk, winner.pk)
        self.assertEqual(Subscriber.objects.count(), 1)

    def test_record_rejects_an_address_too_long_for_the_column(self) -> None:
        email = "a" * 64 + "@" + ".".join(["b" * 63] * 3) + ".com"
        with self.assertRaises(ValueError):
            Subscriber.objects.record(email, source="poll_vote")
        self.assertEqual(Subscriber.objects.count(), 0)

    def test_unsubscribe_tokens_are_unique(self) -> None:
        one, _ = Subscriber.objects.record("one@example.com", source="poll_vote")
        two, _ = Subscriber.objects.record("two@example.com", source="poll_vote")
        self.assertNotEqual(one.unsubscribe_token, two.unsubscribe_token)


class SubscriberStatusConsistencyTests(TestCase):
    """status and unsubscribed_at must agree on every save path, not just
    unsubscribe() — staff editing Status in the admin included."""

    def setUp(self) -> None:
        self.sub, _ = Subscriber.objects.record("a@example.com", source="poll_vote")

    def test_setting_the_status_directly_stamps_the_opt_out(self) -> None:
        self.sub.status = SubscriberStatus.UNSUBSCRIBED
        self.sub.save()
        self.sub.refresh_from_db()
        self.assertIsNotNone(self.sub.unsubscribed_at)

    def test_a_partial_save_of_the_status_stamps_it_too(self) -> None:
        self.sub.status = SubscriberStatus.UNSUBSCRIBED
        self.sub.save(update_fields=["status"])
        self.sub.refresh_from_db()
        self.assertIsNotNone(self.sub.unsubscribed_at)

    def test_an_existing_opt_out_time_is_kept(self) -> None:
        when = timezone.now() - datetime.timedelta(days=3)
        self.sub.status = SubscriberStatus.UNSUBSCRIBED
        self.sub.unsubscribed_at = when
        self.sub.save()
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.unsubscribed_at, when)

    def test_resubscribing_clears_the_opt_out_time(self) -> None:
        self.sub.unsubscribe()
        self.sub.status = SubscriberStatus.ACTIVE
        self.sub.save()
        self.sub.refresh_from_db()
        self.assertIsNone(self.sub.unsubscribed_at)

    def test_the_admin_stamps_an_opt_out(self) -> None:
        from django.contrib.auth.models import User
        from django.urls import reverse

        User.objects.create_superuser(
            username="root", email="root@example.com", password="pw12345"
        )
        self.client.login(username="root", password="pw12345")
        resp = self.client.post(
            reverse("admin:audience_subscriber_change", args=[self.sub.pk]),
            {
                "email": "a@example.com",
                "status": "UNSUBSCRIBED",
                "source": "poll_vote",
                "consent_ip": "",
                "unsubscribed_at_0": "",
                "unsubscribed_at_1": "",
                "changes-TOTAL_FORMS": "0",
                "changes-INITIAL_FORMS": "0",
                "changes-MIN_NUM_FORMS": "0",
                "changes-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriberStatus.UNSUBSCRIBED)
        self.assertIsNotNone(self.sub.unsubscribed_at)


class SubscriptionHistoryTests(TestCase):
    """Every opt-in and opt-out is kept, even after a re-subscribe clears
    unsubscribed_at on the subscriber itself."""

    def setUp(self) -> None:
        self.sub, _ = Subscriber.objects.record("a@example.com", source="poll_vote")

    def history(self) -> list[tuple[str, datetime.datetime]]:
        return list(self.sub.changes.order_by("at", "id").values_list("status", "at"))

    def test_signing_up_records_the_opt_in_at_the_consent_time(self) -> None:
        self.assertEqual(self.history(), [("ACTIVE", self.sub.consent_at)])

    def test_signing_up_again_records_nothing(self) -> None:
        Subscriber.objects.record("a@example.com", source="poll_vote")
        self.assertEqual(len(self.history()), 1)

    def test_unsubscribing_records_the_opt_out_time(self) -> None:
        self.sub.unsubscribe()
        self.assertEqual(self.history()[-1], ("UNSUBSCRIBED", self.sub.unsubscribed_at))

    def test_a_re_subscribe_keeps_the_earlier_opt_out(self) -> None:
        self.sub.unsubscribe()
        opted_out_at = self.sub.unsubscribed_at
        self.sub.status = SubscriberStatus.ACTIVE
        self.sub.save()

        statuses = [status for status, _ in self.history()]
        self.assertEqual(statuses, ["ACTIVE", "UNSUBSCRIBED", "ACTIVE"])
        self.assertIn(("UNSUBSCRIBED", opted_out_at), self.history())
        self.assertIsNone(self.sub.unsubscribed_at)

    def test_a_save_that_does_not_change_the_status_records_nothing(self) -> None:
        self.sub.source = "newsletter"
        self.sub.save()
        self.sub.unsubscribe()
        self.sub.unsubscribe()
        self.assertEqual(len(self.history()), 2)

    def test_the_admin_opt_out_is_recorded(self) -> None:
        from django.contrib.auth.models import User
        from django.urls import reverse

        User.objects.create_superuser(
            username="root", email="root@example.com", password="pw12345"
        )
        self.client.login(username="root", password="pw12345")
        url = reverse("admin:audience_subscriber_change", args=[self.sub.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        resp = self.client.post(
            url,
            {
                "email": "a@example.com",
                "status": "UNSUBSCRIBED",
                "source": "poll_vote",
                "consent_ip": "",
                "unsubscribed_at_0": "",
                "unsubscribed_at_1": "",
                "changes-TOTAL_FORMS": "1",
                "changes-INITIAL_FORMS": "1",
                "changes-MIN_NUM_FORMS": "0",
                "changes-MAX_NUM_FORMS": "1000",
                "changes-0-id": str(self.sub.changes.get().pk),
                "changes-0-subscriber": str(self.sub.pk),
            },
        )
        self.assertEqual(resp.status_code, 302)
        statuses = [status for status, _ in self.history()]
        self.assertEqual(statuses, ["ACTIVE", "UNSUBSCRIBED"])

    def test_the_migration_backfills_existing_subscribers(self) -> None:
        import importlib

        from django.apps import apps

        backfill = importlib.import_module(
            "audience.migrations.0012_subscriptionchange"
        ).backfill
        self.sub.unsubscribe()
        stayed, _ = Subscriber.objects.record("b@example.com", source="poll_vote")
        from audience.models import SubscriptionChange

        SubscriptionChange.objects.all().delete()

        backfill(apps, None)

        self.assertEqual(
            self.history(),
            [
                ("ACTIVE", self.sub.consent_at),
                ("UNSUBSCRIBED", self.sub.unsubscribed_at),
            ],
        )
        self.assertEqual(
            list(stayed.changes.values_list("status", "at")),
            [("ACTIVE", stayed.consent_at)],
        )
