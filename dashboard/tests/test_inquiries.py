from cinema.models import InquiryStatus, SponsorshipInquiry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class InquiryListTests(TestCase):
    def setUp(self) -> None:
        self.staff = get_user_model().objects.create_user(
            username="staff", password="pw", is_staff=True
        )
        self.inquiry = SponsorshipInquiry.objects.create(
            business_name="A.H. Custom Carpentry",
            contact_name="Alex Harper",
            email="alex@example.com",
        )

    def test_requires_staff(self):
        response = self.client.get(reverse("dashboard:inquiries"))
        self.assertNotEqual(response.status_code, 200)

    def test_lists_inquiries(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:inquiries"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A.H. Custom Carpentry")

    def test_tier_renders_as_its_display_label(self):
        # SponsorshipInquiry.tier has no `choices` of its own, so this must
        # not silently fall back to the raw slug ("full_house").
        SponsorshipInquiry.objects.create(
            business_name="Full House Co", contact_name="C",
            email="c@example.com", tier="full_house",
        )
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:inquiries"))
        self.assertContains(response, "Full House")
        self.assertNotContains(response, "full_house")

    def test_new_count_in_context(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:inquiries"))
        self.assertEqual(response.context["new_count"], 1)

    def test_filter_by_status(self):
        SponsorshipInquiry.objects.create(
            business_name="Won Co", contact_name="B", email="b@example.com",
            status=InquiryStatus.WON,
        )
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:inquiries"), {"status": "WON"})
        self.assertContains(response, "Won Co")
        self.assertNotContains(response, "A.H. Custom Carpentry")

    def test_status_can_be_changed(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("dashboard:inquiry_status", args=[self.inquiry.pk]),
            {"status": "CONTACTED"},
        )
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.CONTACTED)

    def test_invalid_status_is_ignored(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("dashboard:inquiry_status", args=[self.inquiry.pk]),
            {"status": "BOGUS"},
        )
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.NEW)
