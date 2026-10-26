"""Conversion tracking.

GA4 recorded zero key events, so there was no way to tell whether a membership
was sold, a gift card bought, or the phone rung.

The load-bearing distinction, and the thing these tests exist to protect: an
outbound click is INTENT and carries no money; only /thanks — which Square
redirects to after payment succeeds — fires revenue. Attaching a value to a
click would make GA4 report sales that never happened.
"""

import re

from django.test import TestCase, override_settings
from django.urls import reverse

from audience.models import MembershipTier


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
    def test_join_click_is_tracked_without_a_value(self):
        # A Join click is intent, not money: the purchase event fires on the
        # order page once Square has confirmed the payment.
        from unittest import mock

        for tier in MembershipTier.objects.all():
            MembershipTier.objects.filter(pk=tier.pk).update(
                square_variation_id=f"VAR-{tier.slug}")
        with mock.patch("web.views.square_enabled", return_value=True):
            html = self.client.get(reverse("membership")).content.decode()
        hits = tracked(html, "membership_join_click")
        self.assertEqual(len(hits), MembershipTier.objects.count())
        for hit in hits:
            self.assertNotIn("value", hit)

    def test_no_giftcard_link_on_the_home_page(self):
        # The gift-card card left the home page on 2026-10-13 (the owner's
        # call). If a gift-card link comes back, tag it giftcard_click.
        html = self.client.get("/").content.decode()
        self.assertEqual(len(tracked(html, "giftcard_click")), 0)

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
        self.assertEqual(len(tracked(html, "rental_email_click")), 0)
        self.assertEqual(len(tracked(html, "rental_inquiry_submit")), 1)


class ThanksPageTests(TestCase):
    def tier(self, slug):
        return MembershipTier.objects.get(slug=slug)

    def test_known_tier_fires_purchase_with_the_real_price(self):
        tier = self.tier("cinema-supporter")
        html = self.client.get("/thanks", {"tier": tier.slug}).content.decode()
        self.assertIn("'purchase'", html)
        self.assertIn(f"value: {tier.price}", html)
        self.assertIn("currency: 'USD'", html)

    def test_value_comes_from_the_record_not_the_query_string(self):
        """Revenue must not be forgeable by editing the URL."""
        tier = self.tier("individual")
        html = self.client.get(
            "/thanks", {"tier": tier.slug, "value": "99999"}
        ).content.decode()
        self.assertIn(f"value: {tier.price}", html)
        self.assertNotIn("99999", html)

    def test_unknown_tier_fires_nothing(self):
        """Better no event than a garbage one."""
        html = self.client.get("/thanks", {"tier": "not-a-tier"}).content.decode()
        self.assertEqual(self.client.get("/thanks", {"tier": "x"}).status_code, 200)
        self.assertNotIn("'purchase'", html)

    def test_missing_tier_fires_nothing(self):
        """Gift cards have a variable amount, so they land here with no tier."""
        html = self.client.get("/thanks").content.decode()
        self.assertNotIn("'purchase'", html)

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
