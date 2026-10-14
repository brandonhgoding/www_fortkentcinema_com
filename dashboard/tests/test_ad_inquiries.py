from cinema.models import AdInquiry, AdType, InquiryStatus
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AdInquiryListTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="staff", password="pw", is_staff=True
        )
        self.inquiry = AdInquiry.objects.create(
            business_name="Rock's Diner",
            contact_name="Pat Harper",
            email="pat@example.com",
            phone="(207) 555-0100",
            ad_type=AdType.VIDEO,
            message="December start?",
        )

    def test_requires_staff(self):
        response = self.client.get(reverse("dashboard:ad_inquiries"))
        self.assertNotEqual(response.status_code, 200)

    def test_lists_inquiries(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:ad_inquiries"))
        self.assertEqual(response.status_code, 200)
        for text in (
            "Rock&#x27;s Diner",
            "Pat Harper",
            "pat@example.com",
            "Video spot",
            "December start?",
        ):
            self.assertContains(response, text)
        self.assertEqual(response.context["new_count"], 1)

    def test_message_is_escaped(self):
        self.inquiry.message = "<script>alert(1)</script>"
        self.inquiry.save()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:ad_inquiries"))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_filter_by_status(self):
        AdInquiry.objects.create(
            business_name="Won Co",
            contact_name="w",
            email="w@example.com",
            status=InquiryStatus.WON,
        )
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("dashboard:ad_inquiries"), {"status": "WON"}
        )
        self.assertContains(response, "Won Co")
        self.assertNotContains(response, "Pat Harper")

    def test_status_can_be_changed(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:ad_inquiry_status", args=[self.inquiry.pk]),
            {"status": "CONTACTED"},
        )
        self.assertRedirects(response, reverse("dashboard:ad_inquiries"))
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.CONTACTED)

    def test_invalid_status_is_ignored(self):
        self.client.force_login(self.staff)
        self.client.post(
            reverse("dashboard:ad_inquiry_status", args=[self.inquiry.pk]),
            {"status": "BOGUS"},
        )
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.NEW)

    def test_status_change_requires_staff(self):
        self.client.post(
            reverse("dashboard:ad_inquiry_status", args=[self.inquiry.pk]),
            {"status": "CONTACTED"},
        )
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.NEW)

    def test_sidebar_links_to_ad_inquiries(self):
        self.client.force_login(self.staff)
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(reverse("dashboard:ad_inquiries"), html)
        self.assertIn("Ad Inquiries", html)

    def test_home_alert_counts_new_ad_inquiries(self):
        AdInquiry.objects.create(
            business_name="Done",
            contact_name="d",
            email="d@example.com",
            status=InquiryStatus.LOST,
        )
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "You have 1 new ad inquiry")
