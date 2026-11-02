from cinema.models import AdInquiry, AdType, HeardFrom, InquiryStatus
from django.test import TestCase
from django.urls import reverse


class AdInquiryTests(TestCase):
    def payload(self, **overrides) -> dict:
        data = {"business_name": "Rock's Diner", "contact_name": "Pat Harper",
                "email": "pat@example.com", "phone": "(207) 555-0100",
                "ad_type": "VIDEO", "message": "We'd like to start in December.",
                "website": ""}
        data.update(overrides)
        return data

    def test_valid_post_creates_an_inquiry(self):
        response = self.client.post(reverse("advertise_inquire"), self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"], f"{reverse('advertise')}?sent=1#inquire"
        )
        row = AdInquiry.objects.get()
        self.assertEqual(row.business_name, "Rock's Diner")
        self.assertEqual(row.contact_name, "Pat Harper")
        self.assertEqual(row.ad_type, AdType.VIDEO)
        self.assertEqual(row.status, InquiryStatus.NEW)

    def test_omitted_ad_type_defaults_to_unsure(self):
        data = self.payload()
        del data["ad_type"]
        self.client.post(reverse("advertise_inquire"), data)
        self.assertEqual(AdInquiry.objects.get().ad_type, AdType.UNSURE)

    def test_bogus_ad_type_is_rejected(self):
        response = self.client.post(
            reverse("advertise_inquire"), self.payload(ad_type="BILLBOARD")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AdInquiry.objects.count(), 0)

    def test_blank_business_name_is_rejected(self):
        response = self.client.post(
            reverse("advertise_inquire"), self.payload(business_name="   ")
        )
        self.assertEqual(AdInquiry.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_invalid_email_is_rejected(self):
        response = self.client.post(
            reverse("advertise_inquire"), self.payload(email="not-an-email")
        )
        self.assertEqual(AdInquiry.objects.count(), 0)
        self.assertContains(response, 'id="id_email_error"')

    def test_overlength_message_is_rejected(self):
        response = self.client.post(
            reverse("advertise_inquire"), self.payload(message="x" * 2001)
        )
        self.assertEqual(AdInquiry.objects.count(), 0)
        self.assertContains(response, "2,000 characters")

    def test_error_response_is_the_full_page(self):
        response = self.client.post(
            reverse("advertise_inquire"), self.payload(email="nope")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "web/advertise.html")
        self.assertContains(response, "Rock&#x27;s Diner")  # values survive

    def test_success_message_is_shown_after_the_redirect(self):
        html = self.client.get(reverse("advertise"), {"sent": "1"}).content.decode()
        self.assertIn("Thanks", html)
        self.assertNotIn('name="business_name"', html)

    def test_honeypot_silently_succeeds_without_a_row(self):
        response = self.client.post(reverse("advertise_inquire"),
                                    self.payload(website="http://spam.example"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("sent=1", response["Location"])
        self.assertEqual(AdInquiry.objects.count(), 0)

    def test_client_ip_is_recorded(self):
        self.client.post(
            reverse("advertise_inquire"), self.payload(), REMOTE_ADDR="203.0.113.9"
        )
        self.assertEqual(AdInquiry.objects.get().ip, "203.0.113.9")

    def test_a_forwarded_header_is_not_trusted(self):
        # X-Forwarded-For is the visitor's to forge; the address comes from
        # REMOTE_ADDR (nginx's X-Real-IP in production).
        response = self.client.post(reverse("advertise_inquire"), self.payload(),
                                    HTTP_X_FORWARDED_FOR="198.51.100.1",
                                    REMOTE_ADDR="203.0.113.9")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AdInquiry.objects.get().ip, "203.0.113.9")

    def test_get_redirects_to_the_page(self):
        self.assertRedirects(
            self.client.get(reverse("advertise_inquire")), reverse("advertise")
        )


class AdInquirySourceTests(TestCase):
    """Most ad leads come by word of mouth or off the screen, which analytics
    cannot see, so the form asks."""

    def post(self, **extra):
        data = {"business_name": "Rock's Diner", "contact_name": "Pat Harper",
                "email": "pat@example.com", "website": ""}
        data.update(extra)
        return self.client.post(reverse("advertise_inquire"), data)

    def test_source_is_stored(self):
        self.post(heard_from=HeardFrom.SCREEN)
        self.assertEqual(AdInquiry.objects.get().heard_from, HeardFrom.SCREEN)

    def test_source_is_optional(self):
        self.post()
        self.assertEqual(AdInquiry.objects.get().heard_from, "")

    def test_bogus_source_is_rejected(self):
        response = self.post(heard_from="TELEPATHY")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AdInquiry.objects.count(), 0)

    def test_question_is_on_the_form(self):
        html = self.client.get(reverse("advertise")).content.decode()
        self.assertIn("How did you hear about us?", html)
        self.assertIn('name="heard_from"', html)
        self.assertIn('<option value="" selected>Choose one</option>', html)


class AdLeadEventTests(TestCase):
    """GA4 used to see only the click on Send, which a validation error
    also produces. The thank-you is the confirmed lead."""

    def test_thank_you_fires_the_lead_event(self):
        html = self.client.get(reverse("advertise"), {"sent": "1"}).content.decode()
        self.assertRegex(
            html, r'data-track-view="generate_lead"[^>]*data-track-form="advertise"'
        )

    def test_the_blank_form_does_not(self):
        html = self.client.get(reverse("advertise")).content.decode()
        self.assertNotIn("generate_lead", html)


class AdsShortLinkTests(TestCase):
    """/ads is what the pre-show slide prints: short enough to type, and
    tagged so GA4 can count the visits the screen sends."""

    def test_redirects_to_the_page_tagged_as_the_screen(self):
        for path in ("/ads", "/ads/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(
                response["Location"],
                "/advertise/?utm_source=fort-kent-cinema&utm_medium=pre-show"
                "&utm_campaign=advertise",
            )
