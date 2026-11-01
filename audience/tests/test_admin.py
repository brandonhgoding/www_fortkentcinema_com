"""The audience admin pages render and validate."""

from django.test import TestCase
from django.urls import reverse

from accounts.tests.factories import make_user
from audience.models import Subscriber


class EmailCaseAdminTests(TestCase):
    """Emails are stored lowercase, so uniqueness must be judged lowercase.

    The admin's default ModelForms check uniqueness before save() lowercases
    the address, so "ADA@" against a stored "ada@" used to pass the check
    and then hit the unique index: an IntegrityError and a 500.
    """

    def setUp(self) -> None:
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")

    def test_subscriber_admin_reports_a_duplicate_in_another_case(self) -> None:
        Subscriber.objects.record("ada@example.com", source="poll_vote")
        resp = self.client.post(
            reverse("admin:audience_subscriber_add"),
            {
                "email": "ADA@Example.com",
                "status": "ACTIVE",
                "source": "admin",
                "consent_ip": "",
                "unsubscribed_at_0": "",
                "unsubscribed_at_1": "",
                "changes-TOTAL_FORMS": "0",
                "changes-INITIAL_FORMS": "0",
                "changes-MIN_NUM_FORMS": "0",
                "changes-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("email", resp.context["adminform"].form.errors)
        self.assertEqual(Subscriber.objects.count(), 1)


class SubscriberAdminConsentTests(TestCase):
    """confirmed_at is the CAN-SPAM consent record: staff must not type it."""

    def setUp(self) -> None:
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")

    def test_admin_created_active_row_has_confirmed_at(self) -> None:
        resp = self.client.post(
            reverse("admin:audience_subscriber_add"),
            {
                "email": "new@example.com",
                "status": "ACTIVE",
                "source": "admin",
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
        sub = Subscriber.objects.get(email="new@example.com")
        self.assertIsNotNone(sub.confirmed_at)

    def test_update_fields_save_persists_the_stamp(self) -> None:
        sub, _ = Subscriber.objects.record("ada@example.com", source="poll_vote")
        Subscriber.objects.filter(pk=sub.pk).update(confirmed_at=None)
        sub.refresh_from_db()
        sub.source = "admin"
        sub.save(update_fields=["source"])
        sub.refresh_from_db()
        self.assertIsNotNone(sub.confirmed_at)

    def test_change_form_shows_both_fields_read_only(self) -> None:
        sub, _ = Subscriber.objects.record("ada@example.com", source="poll_vote")
        resp = self.client.get(
            reverse("admin:audience_subscriber_change", args=[sub.pk])
        )
        self.assertEqual(resp.status_code, 200)
        form = resp.context["adminform"].form
        self.assertNotIn("confirmed_at", form.fields)
        self.assertNotIn("confirmation_sent_at", form.fields)
        self.assertContains(resp, "field-confirmed_at")
        self.assertContains(resp, "field-confirmation_sent_at")


class SubscriptionHistoryAdminTests(TestCase):
    """The opt-in/opt-out history is the consent record: the subscriber's
    admin page shows it but cannot add, edit or delete rows."""

    def setUp(self) -> None:
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")
        self.sub, _ = Subscriber.objects.record("ada@example.com", source="poll_vote")
        self.url = reverse("admin:audience_subscriber_change", args=[self.sub.pk])

    def payload(self, **extra: str) -> dict:
        change = self.sub.changes.get()
        return {
            "email": "ada@example.com",
            "status": "ACTIVE",
            "source": "poll_vote",
            "consent_ip": "",
            "unsubscribed_at_0": "",
            "unsubscribed_at_1": "",
            "changes-TOTAL_FORMS": "1",
            "changes-INITIAL_FORMS": "1",
            "changes-MIN_NUM_FORMS": "0",
            "changes-MAX_NUM_FORMS": "1000",
            "changes-0-id": str(change.pk),
            "changes-0-subscriber": str(self.sub.pk),
            **extra,
        }

    def test_inline_offers_no_add_and_no_delete(self) -> None:
        resp = self.client.get(self.url)
        [inline] = resp.context["inline_admin_formsets"]
        self.assertFalse(inline.has_add_permission)
        self.assertFalse(inline.formset.can_delete)

    def test_a_posted_delete_keeps_the_row(self) -> None:
        before = list(self.sub.changes.values_list("pk", "status", "at"))
        resp = self.client.post(self.url, self.payload(**{"changes-0-DELETE": "on"}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            list(self.sub.changes.values_list("pk", "status", "at")), before
        )

    def test_a_posted_new_row_is_not_saved(self) -> None:
        data = self.payload(
            **{
                "changes-TOTAL_FORMS": "2",
                "changes-1-status": "UNSUBSCRIBED",
                "changes-1-at_0": "2026-01-01",
                "changes-1-at_1": "12:00:00",
                "changes-1-subscriber": str(self.sub.pk),
            }
        )
        self.client.post(self.url, data)
        self.assertEqual(self.sub.changes.count(), 1)
