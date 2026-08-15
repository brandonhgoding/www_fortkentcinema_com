"""Conversion tracking.

GA4 recorded zero key events, so there was no way to tell whether a gift card
was bought or the phone rung.

The load-bearing distinction, and the thing these tests exist to protect: an
outbound click is INTENT and carries no money. Attaching a value to a click
would make GA4 report sales that never happened. /thanks used to be the one
place revenue was fired, for memberships; that program was discontinued
2026-08-14, so nothing on the site fires `purchase` any more and the tests
below pin that no click has quietly picked up a value in its place.
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

    @override_settings(GA_MEASUREMENT_ID="G-TESTID123")
    def test_hardcoded_id_is_gone(self):
        """It used to be baked into base.html."""
        html = self.client.get("/").content.decode()
        self.assertNotIn("G-S2PR27SWGD", html)


class ClickEventMarkupTests(TestCase):
    def test_giftcard_click_carries_no_monetary_value(self):
        """A click is not a purchase — and a gift card's amount is variable, so
        there is no value to attach even in principle."""
        html = self.client.get("/").content.decode()
        for hit in tracked(html, "giftcard_click"):
            self.assertNotIn("data-track-value", hit)
            self.assertNotIn("data-track-price", hit)

    def test_giftcard_tagged(self):
        html = self.client.get("/").content.decode()
        self.assertEqual(len(tracked(html, "giftcard_click")), 1)

    def test_footer_phone_tagged_with_location(self):
        html = self.client.get("/").content.decode()
        hits = tracked(html, "phone_click")
        self.assertEqual(len(hits), 1)
        self.assertIn('data-track-location="footer"', hits[0])

    def test_rentals_phone_and_email_tagged(self):
        html = self.client.get(reverse("rentals")).content.decode()
        self.assertIn('data-track-location="rentals"', html)
        self.assertEqual(len(tracked(html, "rental_email_click")), 1)


class ThanksPageTests(TestCase):
    def test_fires_no_purchase_event(self):
        """The membership tiers this page priced are gone. Gift cards, the only
        thing still sold through Square, have a variable amount — there is no
        value to report, and a fabricated one would be worse than silence."""
        html = self.client.get("/thanks").content.decode()
        self.assertNotIn("'purchase'", html)

    def test_stale_tier_links_still_render(self):
        """Old Square redirects and bookmarks carry ?tier=<slug>. They must land
        on a working thank-you, not a 500 or a garbage event."""
        resp = self.client.get("/thanks", {"tier": "cinema-supporter"})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertNotIn("'purchase'", html)
        self.assertNotIn("cinema-supporter", html)

    def test_page_is_noindex(self):
        html = self.client.get("/thanks").content.decode()
        self.assertIn('<meta name="robots" content="noindex, nofollow" />', html)

    def test_only_one_robots_tag(self):
        """A noindex sitting next to an index,follow is a coin flip."""
        html = self.client.get("/thanks").content.decode()
        self.assertEqual(len(re.findall(r'<meta name="robots"', html)), 1)

    def test_absent_from_sitemap(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("/thanks", xml)

    def test_other_pages_remain_indexable(self):
        html = self.client.get("/").content.decode()
        self.assertIn('<meta name="robots" content="index, follow" />', html)
