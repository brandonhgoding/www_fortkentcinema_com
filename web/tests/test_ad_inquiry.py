from cinema.models import AdInquiry, AdType, InquiryStatus
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
        self.assertContains(response, "valid email")
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
        self.assertContains(response, "QUESTIONS WE GET")
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

    def test_malformed_forwarded_header_does_not_500(self):
        response = self.client.post(reverse("advertise_inquire"), self.payload(),
                                    HTTP_X_FORWARDED_FOR="not-an-ip")
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(AdInquiry.objects.get().ip)

    def test_get_redirects_to_the_page(self):
        self.assertRedirects(
            self.client.get(reverse("advertise_inquire")), reverse("advertise")
        )
