import json
import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from web.constants import AD_SLIDE_PRICE, AD_VIDEO_PRICE, ADVERTISING_FAQ


class AdvertisePageTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("advertise"))
        self.html = self.response.content.decode()

    def test_renders(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertTemplateUsed(self.response, "web/advertise.html")
        self.assertIn(
            "<title>Advertise on the Big Screen | Fort Kent Cinema</title>",
            self.html,
        )
        self.assertIn("YOUR BUSINESS ON THE BIG SCREEN", self.html)

    def test_the_two_rates(self):
        for text in ("PRE-SHOW SLIDE", "VIDEO SPOT", "$75", "$150", "30 seconds",
                     "1920", "PNG or JPEG", "MP4", "THE RATES", "HOW IT WORKS"):
            self.assertIn(text, self.html, text)
        # Nothing promises a count.
        self.assertNotRegex(self.html, r"\d[\d,]* (people|views|plays)")

    def test_exposure_promise(self):
        self.assertIn("before every show", self.html)
        self.assertIn("30 minutes before showtime", self.html)

    def test_how_it_works_names_the_deadline_and_square(self):
        self.assertIn("by the 20th", self.html)
        self.assertIn("invoice you through Square", self.html)

    def test_faq_renders_once_visibly_and_once_as_json_ld(self):
        for faq in ADVERTISING_FAQ:
            self.assertEqual(self.html.count(faq["question"]), 2, faq["question"])
        # base.html emits its own MovieTheater block first, so look at every
        # JSON-LD block and take this page's FAQPage one.
        blocks = [
            json.loads(raw)
            for raw in re.findall(
                r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                self.html, re.S,
            )
        ]
        data = next((b for b in blocks if b.get("@type") == "FAQPage"), {"@type": None})
        self.assertEqual(data["@type"], "FAQPage")
        self.assertEqual([q["name"] for q in data["mainEntity"]],
                         [f["question"] for f in ADVERTISING_FAQ])

    def test_policy_is_on_the_page(self):
        self.assertIn("political", self.html)
        self.assertIn("decline any ad", self.html)

    def test_form_is_on_the_page(self):
        self.assertIn('id="inquire"', self.html)
        self.assertIn(f'action="{reverse("advertise_inquire")}"', self.html)
        self.assertIn('name="business_name"', self.html)
        self.assertIn('name="email"', self.html)
        self.assertEqual(self.html.count('name="ad_type"'), 3)
        self.assertIn("Pre-show slide, $75 a month", self.html)
        # Radios sit in a fieldset, not nested inside another <label>.
        self.assertIn("<fieldset", self.html)
        self.assertNotRegex(
            self.html,
            r"<label[^>]*>\s*<span[^>]*>What are you interested in\?",
        )

    def test_og_image_is_the_card_art(self):
        self.assertRegex(
            self.html,
            r'<meta property="og:image" '
            r'content="[^"]*img/involved/your-ad-here\.jpg" />',
        )
        self.assertIn('<meta property="og:image:width" content="1200" />', self.html)
        self.assertIn('<meta property="og:image:height" content="675" />', self.html)
        self.assertRegex(
            self.html, r'<meta property="og:image:alt" content="[^"]{10,}" />'
        )

    def test_phone_fallback(self):
        self.assertIn("Or call", self.html)
        self.assertIn(
            'data-track="phone_click" data-track-location="advertise"', self.html
        )


class AdvertiseMetaPriceTests(TestCase):
    """The search snippet and the social card quote the rates too, so they
    render from the constants like the cards do; a typed-in price would go
    stale the day the rate changes."""

    def meta(self, html: str, attr: str) -> str:
        return re.search(rf'<meta {attr} content="([^"]*)"', html).group(1)

    def test_meta_descriptions_carry_the_constant_prices(self):
        html = self.client.get(reverse("advertise")).content.decode()
        for attr in ('name="description"', 'property="og:description"'):
            content = self.meta(html, attr)
            self.assertIn(f"${AD_SLIDE_PRICE} a month", content, attr)
            self.assertIn(f"${AD_VIDEO_PRICE}", content, attr)

    def test_meta_descriptions_follow_a_rate_change(self):
        with mock.patch("web.views.AD_SLIDE_PRICE", 81), \
                mock.patch("web.views.AD_VIDEO_PRICE", 163):
            html = self.client.get(reverse("advertise")).content.decode()
        for attr in ('name="description"', 'property="og:description"'):
            content = self.meta(html, attr)
            self.assertIn("$81 a month", content, attr)
            self.assertIn("$163", content, attr)
