from django.test import TestCase

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

    def test_unsubscribe_tokens_are_unique(self) -> None:
        one, _ = Subscriber.objects.record("one@example.com", source="poll_vote")
        two, _ = Subscriber.objects.record("two@example.com", source="poll_vote")
        self.assertNotEqual(one.unsubscribe_token, two.unsubscribe_token)
