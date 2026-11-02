"""Conversion tracking.

GA4 recorded zero key events, so there was no way to tell whether the phone
rang or an inquiry was sent. A click is intent and carries no money; nothing
is paid for on the site.
"""

import re

from django.test import TestCase, override_settings
from django.urls import reverse


def tracked(html, event):
    """Elements carrying data-track="<event>"."""
    return re.findall(rf'data-track="{event}"[^>]*', html)


class GA4SnippetTests(TestCase):
    def test_no_gtag_when_measurement_id_unset(self):
        """The default everywhere but production — which is what stops local dev
        from polluting the analytics we're about to start trusting."""
        html = self.client.get("/").content.decode()
        self.assertNotIn("googletagmanager.com", html)

    @override_settings(GA_MEASUREMENT_ID="G-TESTID123")
    def test_gtag_rendered_with_configured_id(self):
        html = self.client.get("/").content.decode()
        self.assertIn("googletagmanager.com/gtag/js?id=G-TESTID123", html)
        self.assertIn("gtag('config', 'G-TESTID123')", html)


class ClickEventMarkupTests(TestCase):
    def test_footer_phone_tagged_with_location(self):
        html = self.client.get("/").content.decode()
        hits = tracked(html, "phone_click")
        self.assertEqual(len(hits), 1)
        self.assertIn('data-track-location="footer"', hits[0])

    def test_rentals_phone_and_inquiry_tagged(self):
        """The personal-email link became an inquiry form; its submit button
        carries the tracking the mailto link used to."""
        html = self.client.get(reverse("rentals")).content.decode()
        self.assertIn('data-track-location="rentals"', html)
        self.assertEqual(len(tracked(html, "rental_inquiry_submit")), 1)


class LeadViewEventTests(TestCase):
    """Both inquiry thank-yous fire generate_lead on load: the confirmed
    lead, where the Send click is only intent."""

    def test_rentals_thank_you_fires_the_lead_event(self):
        html = self.client.get(reverse("rentals"), {"sent": "1"}).content.decode()
        self.assertRegex(
            html, r'data-track-view="generate_lead"[^>]*data-track-form="rentals"'
        )


class RobotsTests(TestCase):
    def test_other_pages_remain_indexable(self):
        html = self.client.get("/").content.decode()
        self.assertIn('<meta name="robots" content="index, follow" />', html)
