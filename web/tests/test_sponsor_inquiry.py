import datetime

from cinema.models import InquiryStatus, SponsorshipInquiry, Studio, StudioTitle
from django.test import TestCase
from django.urls import reverse


class SponsorInquiryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        studio = Studio.objects.create(name="Universal Pictures", slug="universal")
        cls.title = StudioTitle.objects.create(
            studio=studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20),
        )

    def payload(self, **overrides) -> dict:
        data = {
            "business_name": "A.H. Custom Carpentry",
            "contact_name": "Alex Harper",
            "email": "alex@example.com",
            "phone": "(207) 555-0100",
            "tier": "presenting",
            "studio_title": self.title.pk,
            "message": "We'd like the end of the month.",
            "website": "",
        }
        data.update(overrides)
        return data

    def test_valid_post_creates_an_inquiry(self):
        response = self.client.post(reverse("sponsor_inquire"), self.payload())
        # Post/Redirect/Get: a refresh must not resubmit the form.
        self.assertEqual(response.status_code, 302)
        self.assertIn("sent=1", response["Location"])

        inquiry = SponsorshipInquiry.objects.get()
        self.assertEqual(inquiry.business_name, "A.H. Custom Carpentry")
        self.assertEqual(inquiry.email, "alex@example.com")
        self.assertEqual(inquiry.tier, "presenting")
        self.assertEqual(inquiry.studio_title, self.title)
        self.assertEqual(inquiry.status, InquiryStatus.NEW)

    def test_success_message_is_shown_after_the_redirect(self):
        html = self.client.get(
            reverse("sponsor"), {"sent": "1"}
        ).content.decode()
        self.assertIn("Thanks", html)

    def test_error_response_is_a_full_page_not_a_fragment(self):
        # There is no htmx on public pages, so a failed POST must re-render
        # the whole page — nav, styles and all — rather than a bare partial.
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(email="nope")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/sponsor.html")

    def test_error_response_still_lists_the_catalog(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(email="nope")
        )
        self.assertContains(response, "Jaws")

    def test_title_is_optional(self):
        self.client.post(reverse("sponsor_inquire"), self.payload(studio_title=""))
        self.assertIsNone(SponsorshipInquiry.objects.get().studio_title)

    def test_tier_is_optional(self):
        self.client.post(reverse("sponsor_inquire"), self.payload(tier=""))
        self.assertEqual(SponsorshipInquiry.objects.get().tier, "")

    def test_missing_business_name_is_rejected(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(business_name="")
        )
        self.assertEqual(SponsorshipInquiry.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_invalid_email_is_rejected(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(email="not-an-email")
        )
        self.assertEqual(SponsorshipInquiry.objects.count(), 0)
        self.assertContains(response, "valid email")

    def test_submitted_values_survive_a_validation_error(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(email="nope")
        )
        self.assertContains(response, "A.H. Custom Carpentry")

    def test_honeypot_silently_succeeds_without_creating_a_row(self):
        response = self.client.post(
            reverse("sponsor_inquire"), self.payload(website="http://spam.example")
        )
        # Indistinguishable from success, so a bot learns nothing.
        self.assertEqual(response.status_code, 302)
        self.assertIn("sent=1", response["Location"])
        self.assertEqual(SponsorshipInquiry.objects.count(), 0)

    def test_client_ip_is_recorded(self):
        self.client.post(
            reverse("sponsor_inquire"), self.payload(), REMOTE_ADDR="203.0.113.9"
        )
        self.assertEqual(SponsorshipInquiry.objects.get().ip, "203.0.113.9")

    def test_get_redirects_to_the_page(self):
        response = self.client.get(reverse("sponsor_inquire"))
        self.assertRedirects(response, reverse("sponsor"))


class SponsorFormRenderTests(TestCase):
    def test_form_is_on_the_sponsor_page(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn('name="business_name"', html)
        self.assertIn('name="email"', html)
        self.assertIn('id="inquire"', html)
