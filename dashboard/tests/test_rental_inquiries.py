import datetime

from cinema.models import InquiryStatus, RentalInquiry
from django.test import TestCase
from django.urls import reverse
from dashboard.tests.helpers import make_staff


class RentalInquiryListTests(TestCase):
    def setUp(self) -> None:
        self.staff = make_staff(
            email="staff@example.com", password="pw"
        )
        self.inquiry = RentalInquiry.objects.create(
            contact_name="Alex Harper",
            email="alex@example.com",
            preferred_date=datetime.date(2026, 11, 14),
            guests=25,
            event_type="Birthday party",
        )

    def test_requires_staff(self):
        response = self.client.get(reverse("dashboard:rental_inquiries"))
        self.assertNotEqual(response.status_code, 200)

    def test_lists_inquiries(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:rental_inquiries"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alex Harper")
        self.assertContains(response, "Birthday party")
        self.assertContains(response, "Nov 14, 2026")

    def test_new_count_in_context(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:rental_inquiries"))
        self.assertEqual(response.context["new_count"], 1)

    def test_filter_by_status(self):
        RentalInquiry.objects.create(
            contact_name="Won Person", email="b@example.com",
            status=InquiryStatus.WON,
        )
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("dashboard:rental_inquiries"), {"status": "WON"}
        )
        self.assertContains(response, "Won Person")
        self.assertNotContains(response, "Alex Harper")

    def test_status_can_be_changed(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:rental_inquiry_status", args=[self.inquiry.pk]),
            {"status": "CONTACTED"},
        )
        self.assertRedirects(response, reverse("dashboard:rental_inquiries"))
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.CONTACTED)

    def test_invalid_status_is_ignored(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("dashboard:rental_inquiry_status", args=[self.inquiry.pk]),
            {"status": "BOGUS"},
        )
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.NEW)

    def test_status_change_requires_staff(self):
        self.client.post(
            reverse("dashboard:rental_inquiry_status", args=[self.inquiry.pk]),
            {"status": "CONTACTED"},
        )
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.NEW)

    def test_sidebar_links_to_rental_inquiries(self):
        self.client.force_login(self.staff)
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(reverse("dashboard:rental_inquiries"), html)

    def test_home_alert_counts_new_rental_inquiries(self):
        RentalInquiry.objects.create(
            contact_name="Done", email="d@example.com",
            status=InquiryStatus.LOST,
        )
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "You have 1 new rental inquiry")


class RentalInquiryViewOnlyTests(TestCase):
    def test_view_only_user_sees_status_as_text(self):
        inquiry = RentalInquiry.objects.create(
            contact_name="Alex Harper", email="alex@example.com"
        )
        make_staff(
            email="viewer@example.com",
            password="pw",
            perms=("cinema.view_rentalinquiry",),
        )
        self.client.login(username="viewer@example.com", password="pw")
        response = self.client.get(reverse("dashboard:rental_inquiries"))
        self.assertContains(response, "Alex Harper")
        self.assertNotContains(
            response,
            reverse("dashboard:rental_inquiry_status", args=[inquiry.pk]),
        )
        self.assertContains(response, inquiry.get_status_display() + "\n")
