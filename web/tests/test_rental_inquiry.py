import datetime

from cinema.models import InquiryStatus, RentalInquiry
from django.test import TestCase
from django.urls import reverse


class RentalInquiryTests(TestCase):
    def payload(self, **overrides) -> dict:
        data = {
            "contact_name": "Alex Harper",
            "email": "alex@example.com",
            "phone": "(207) 555-0100",
            "preferred_date": "2026-11-14",
            "guests": "25",
            "event_type": "Birthday, our own DVD",
            "message": "Saturday afternoon if you have it.",
            "website": "",
        }
        data.update(overrides)
        return data

    def test_valid_post_creates_an_inquiry(self):
        response = self.client.post(reverse("rentals_inquire"), self.payload())
        # Post/Redirect/Get: a refresh must not resubmit the form.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"], f"{reverse('rentals')}?sent=1#inquire"
        )

        inquiry = RentalInquiry.objects.get()
        self.assertEqual(inquiry.contact_name, "Alex Harper")
        self.assertEqual(inquiry.email, "alex@example.com")
        self.assertEqual(inquiry.phone, "(207) 555-0100")
        self.assertEqual(inquiry.preferred_date, datetime.date(2026, 11, 14))
        self.assertEqual(inquiry.guests, 25)
        self.assertEqual(inquiry.event_type, "Birthday, our own DVD")
        self.assertEqual(inquiry.status, InquiryStatus.NEW)

    def test_only_name_and_email_are_required(self):
        response = self.client.post(
            reverse("rentals_inquire"),
            self.payload(
                phone="", preferred_date="", guests="", event_type="", message=""
            ),
        )
        self.assertEqual(response.status_code, 302)
        inquiry = RentalInquiry.objects.get()
        self.assertIsNone(inquiry.preferred_date)
        self.assertIsNone(inquiry.guests)

    def test_success_message_is_shown_after_the_redirect(self):
        html = self.client.get(reverse("rentals"), {"sent": "1"}).content.decode()
        self.assertIn("Thanks", html)
        self.assertNotIn('name="contact_name"', html)

    def test_error_response_is_a_full_page_not_a_fragment(self):
        # No htmx on public pages, so a failed POST re-renders the whole page.
        response = self.client.post(
            reverse("rentals_inquire"), self.payload(email="nope")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/rentals.html")
        # The rest of the page is still there, FAQ and all.
        self.assertContains(response, "QUESTIONS WE GET")

    def test_missing_name_is_rejected(self):
        response = self.client.post(
            reverse("rentals_inquire"), self.payload(contact_name="")
        )
        self.assertEqual(RentalInquiry.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_invalid_email_is_rejected(self):
        response = self.client.post(
            reverse("rentals_inquire"), self.payload(email="not-an-email")
        )
        self.assertEqual(RentalInquiry.objects.count(), 0)
        self.assertContains(response, "valid email")

    def test_zero_guests_is_rejected(self):
        self.client.post(reverse("rentals_inquire"), self.payload(guests="0"))
        self.assertEqual(RentalInquiry.objects.count(), 0)

    def test_submitted_values_survive_a_validation_error(self):
        response = self.client.post(
            reverse("rentals_inquire"), self.payload(email="nope")
        )
        self.assertContains(response, "Alex Harper")

    def test_overlength_message_is_rejected(self):
        # Cap the message: an anonymous POST lands in a TextField.
        response = self.client.post(
            reverse("rentals_inquire"), self.payload(message="x" * 2001)
        )
        self.assertEqual(RentalInquiry.objects.count(), 0)
        self.assertContains(response, "2,000 characters")

    def test_honeypot_silently_succeeds_without_creating_a_row(self):
        response = self.client.post(
            reverse("rentals_inquire"),
            self.payload(website="http://spam.example"),
        )
        # Indistinguishable from success, so a bot learns nothing.
        self.assertEqual(response.status_code, 302)
        self.assertIn("sent=1", response["Location"])
        self.assertEqual(RentalInquiry.objects.count(), 0)

    def test_client_ip_is_recorded(self):
        self.client.post(
            reverse("rentals_inquire"), self.payload(), REMOTE_ADDR="203.0.113.9"
        )
        self.assertEqual(RentalInquiry.objects.get().ip, "203.0.113.9")

    def test_malformed_forwarded_header_does_not_500(self):
        response = self.client.post(
            reverse("rentals_inquire"),
            self.payload(),
            HTTP_X_FORWARDED_FOR="not-an-ip",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(RentalInquiry.objects.get().ip)

    def test_get_redirects_to_the_page(self):
        response = self.client.get(reverse("rentals_inquire"))
        self.assertRedirects(response, reverse("rentals"))


class RentalFormRenderTests(TestCase):
    def setUp(self) -> None:
        self.html = self.client.get(reverse("rentals")).content.decode()

    def test_form_is_on_the_rentals_page(self):
        self.assertIn('id="inquire"', self.html)
        self.assertIn(f'action="{reverse("rentals_inquire")}"', self.html)
        self.assertIn('name="contact_name"', self.html)
        self.assertIn('name="email"', self.html)

    def test_inputs_have_the_right_types(self):
        self.assertRegex(self.html, r'type="date"[^>]*name="preferred_date"')
        self.assertRegex(self.html, r'type="number"[^>]*name="guests"[^>]*min="1"')

    def test_fields_sit_inside_real_labels(self):
        self.assertRegex(self.html, r'<label[^>]*>\s*<span[^>]*>Your name')

    def test_personal_email_is_gone(self):
        # The owner's personal Gmail used to be the only written contact.
        self.assertNotIn("gmail", self.html.lower())
        self.assertNotIn("mailto:", self.html)

    def test_phone_stays_as_the_alternative(self):
        self.assertIn('href="tel:+12072315287"', self.html)

    def test_form_uses_rental_classes(self):
        # The form owns its styles; it must not lean on the sponsor page's.
        self.assertIn("rental-inquire__form", self.html)
        self.assertNotIn("sponsor-inquire", self.html)
