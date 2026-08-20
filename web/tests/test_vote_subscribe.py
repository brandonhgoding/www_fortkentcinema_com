from django.test import TestCase
from django.urls import reverse

from audience.models import Subscriber, SubscriberStatus


class VoteSubscribeTests(TestCase):
    def test_records_the_address(self) -> None:
        response = self.client.post(
            reverse("vote_subscribe"),
            {"email": "Fan@Example.com"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        sub = Subscriber.objects.get()
        self.assertEqual(sub.email, "fan@example.com")
        self.assertEqual(sub.source, "poll_vote")
        self.assertEqual(sub.status, SubscriberStatus.ACTIVE)

    def test_consent_ip_is_recorded(self) -> None:
        self.client.post(
            reverse("vote_subscribe"),
            {"email": "fan@example.com"},
            HTTP_HX_REQUEST="true",
            REMOTE_ADDR="198.51.100.4",
        )
        self.assertEqual(Subscriber.objects.get().consent_ip, "198.51.100.4")

    def test_signing_up_twice_is_not_an_error(self) -> None:
        for _ in range(2):
            response = self.client.post(
                reverse("vote_subscribe"),
                {"email": "fan@example.com"},
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(Subscriber.objects.count(), 1)

    def test_unsubscribed_address_is_not_resurrected(self) -> None:
        sub, _ = Subscriber.objects.record("gone@example.com", source="poll_vote")
        sub.unsubscribe()

        self.client.post(
            reverse("vote_subscribe"),
            {"email": "gone@example.com"},
            HTTP_HX_REQUEST="true",
        )

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriberStatus.UNSUBSCRIBED)

    def test_honeypot_silently_discards_the_submission(self) -> None:
        response = self.client.post(
            reverse("vote_subscribe"),
            {"email": "bot@example.com", "website": "http://spam.example"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Subscriber.objects.count(), 0)

    def test_invalid_address_is_reported_not_saved(self) -> None:
        response = self.client.post(
            reverse("vote_subscribe"),
            {"email": "not-an-email"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("valid email", response.content.decode())
        self.assertEqual(Subscriber.objects.count(), 0)

    def test_blank_address_is_reported_not_saved(self) -> None:
        response = self.client.post(
            reverse("vote_subscribe"), {"email": "  "}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Subscriber.objects.count(), 0)

    def test_copy_does_not_promise_a_newsletter(self) -> None:
        response = self.client.post(
            reverse("vote_subscribe"),
            {"email": "fan@example.com"},
            HTTP_HX_REQUEST="true",
        )
        html = response.content.decode().lower()
        self.assertNotIn("newsletter", html)
        self.assertNotIn("weekly", html)
