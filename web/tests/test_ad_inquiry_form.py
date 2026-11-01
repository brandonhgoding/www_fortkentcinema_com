from cinema.models import AdType
from django.test import TestCase
from web.constants import AD_SLIDE_PRICE, AD_VIDEO_PRICE
from web.forms import AdInquiryForm


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
        self.assertIn(f"${AD_SLIDE_PRICE}", html)
        self.assertIn(f"${AD_VIDEO_PRICE}", html)

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
        self.assertIn("message", form.errors)

    def test_honeypot(self):
        spam = self.data(website="http://spam.example")
        self.assertTrue(AdInquiryForm(spam).is_bot)
        self.assertFalse(AdInquiryForm(self.data()).is_bot)
