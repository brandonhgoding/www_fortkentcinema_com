from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from audience.models import Subscriber

User = get_user_model()


class SubscriberListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:subscribers")).content.decode()
        self.assertIn("empty-state", html)

    def test_lists_addresses_and_a_count(self) -> None:
        Subscriber.objects.record("a@example.com", source="poll_vote")
        Subscriber.objects.record("b@example.com", source="poll_vote")
        html = self.client.get(reverse("dashboard:subscribers")).content.decode()
        self.assertIn("a@example.com", html)
        self.assertIn("2", html)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:subscribers")).status_code, 302
        )

    def test_sidebar_links_to_subscribers(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(reverse("dashboard:subscribers"), html)

    def test_pending_shows_its_label_and_is_not_counted_or_exported(self) -> None:
        Subscriber.objects.record("in@example.com", source="poll_vote")
        Subscriber.objects.request_signup("wait@example.com", "movie_page")
        response = self.client.get(reverse("dashboard:subscribers"))
        html = response.content.decode()
        self.assertIn("Pending confirmation", html)
        self.assertIn("status-pending", html)
        self.assertEqual(response.context["active_count"], 1)
        body = self.client.get(
            reverse("dashboard:subscribers_export")
        ).content.decode()
        self.assertIn("in@example.com", body)
        self.assertNotIn("wait@example.com", body)


class SubscriberExportTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_export_is_a_csv_attachment(self) -> None:
        response = self.client.get(reverse("dashboard:subscribers_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("subscribers", response["Content-Disposition"])

    def test_export_has_a_header_row(self) -> None:
        body = self.client.get(
            reverse("dashboard:subscribers_export")
        ).content.decode()
        self.assertTrue(body.startswith("email,source,consent_at"))

    def test_export_contains_active_addresses(self) -> None:
        Subscriber.objects.record("a@example.com", source="poll_vote")
        body = self.client.get(
            reverse("dashboard:subscribers_export")
        ).content.decode()
        self.assertIn("a@example.com", body)

    def test_export_excludes_unsubscribed_addresses(self) -> None:
        Subscriber.objects.record("stay@example.com", source="poll_vote")
        gone, _ = Subscriber.objects.record("gone@example.com", source="poll_vote")
        gone.unsubscribe()

        body = self.client.get(
            reverse("dashboard:subscribers_export")
        ).content.decode()

        self.assertIn("stay@example.com", body)
        self.assertNotIn("gone@example.com", body)

    def test_export_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:subscribers_export")).status_code, 302
        )
