from cinema.models import AdType
from django.test import SimpleTestCase, TestCase
from web.constants import (
    AD_ARTWORK_DEADLINE_DAY,
    AD_SLIDE_PRICE,
    AD_VIDEO_MAX_SECONDS,
    AD_VIDEO_PRICE,
    ADVERTISING_FAQ,
)
from web.forms import AdInquiryForm


class AdvertisingConstantsTests(SimpleTestCase):
    def test_the_rates(self):
        self.assertEqual(
            (
                AD_SLIDE_PRICE,
                AD_VIDEO_PRICE,
                AD_VIDEO_MAX_SECONDS,
                AD_ARTWORK_DEADLINE_DAY,
            ),
            (75, 150, 30, 20),
        )

    def test_faq_reads_from_the_constants(self):
        questions = [f["question"] for f in ADVERTISING_FAQ]
        self.assertEqual(questions, [
            "When does my ad start?", "How do I pay?", "Can I change my ad?",
            "What are the specs?", "Is there a contract?",
            "Do you run every ad?",
        ])
        answers = " ".join(f["answer"] for f in ADVERTISING_FAQ)
        self.assertIn("by the 20th", answers)
        self.assertIn("up to 30 seconds", answers)
        self.assertIn("political", answers)
        self.assertIn("Square invoice", answers)


class AdInquiryFormTests(TestCase):
    def data(self, **overrides):
        d = {
            "business_name": "Rock's Diner", "contact_name": "Pat",
            "email": "pat@example.com", "phone": "", "ad_type": "SLIDE",
            "message": "", "website": "",
        }
        d.update(overrides)
        return d

    def test_radio_labels_carry_the_prices(self):
        html = str(AdInquiryForm()["ad_type"])
        self.assertEqual(html.count('type="radio"'), 3)
        self.assertIn("Pre-show slide, $75 a month", html)
        self.assertIn("Video spot, $150 a month", html)
        self.assertIn("Not sure yet", html)

    def test_required_fields(self):
        form = AdInquiryForm(self.data(phone="", ad_type="", message=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ad_type"], AdType.UNSURE)
        self.assertFalse(AdInquiryForm(self.data(business_name="")).is_valid())
        self.assertFalse(AdInquiryForm(self.data(contact_name="")).is_valid())
        self.assertFalse(AdInquiryForm(self.data(email="nope")).is_valid())

    def test_bogus_ad_type_is_rejected(self):
        form = AdInquiryForm(self.data(ad_type="BILLBOARD"))
        self.assertFalse(form.is_valid())
        self.assertIn("ad_type", form.errors)

    def test_message_is_capped(self):
        form = AdInquiryForm(self.data(message="x" * 2001))
        self.assertFalse(form.is_valid())
        self.assertIn("2,000 characters", form.errors["message"][0])

    def test_honeypot(self):
        spam = self.data(website="http://spam.example")
        self.assertTrue(AdInquiryForm(spam).is_bot)
        self.assertFalse(AdInquiryForm(self.data()).is_bot)

    def test_labels(self):
        labels = {n: f.label for n, f in AdInquiryForm().fields.items()}
        self.assertEqual(labels["business_name"], "Business name")
        self.assertEqual(labels["contact_name"], "Your name")
        self.assertEqual(labels["phone"], "Phone (optional)")
        self.assertEqual(labels["ad_type"], "What are you interested in?")
        self.assertEqual(labels["message"], "Anything else? (optional)")
