"""The home page's Membership band, straight after the showtimes."""

import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from audience.models import MembershipTier


PRICE_35 = 'From <span class="home-membership__amount">$35</span> a year.'


@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_now_showing", return_value=[])
class HomeMembershipBandTests(TestCase):
    def setUp(self) -> None:
        # Migrations seed the real tiers; these tests set their own prices.
        MembershipTier.objects.all().delete()

    def _tier(
        self, slug: str, price: int, listed: bool = True, months: int = 12
    ) -> None:
        MembershipTier.objects.create(
            slug=slug,
            name=slug.title(),
            price=price,
            show_on_membership_page=listed,
            duration_months=months,
        )

    def _html(self) -> str:
        return self.client.get(reverse("home")).content.decode()

    def test_band_renders_after_now_showing(self, _ns, _cs) -> None:
        html = self._html()
        self.assertEqual(html.count('id="membership"'), 1)
        self.assertLess(html.index('id="now-showing"'), html.index('id="membership"'))
        self.assertLess(html.index('id="membership"'), html.index('id="coming-soon"'))

    def test_price_is_cheapest_listed_tier(self, _ns, _cs) -> None:
        self._tier("standard", 60)
        self._tier("senior", 35)
        self._tier("retired", 10, listed=False)
        html = self._html()
        self.assertIn(PRICE_35, html)
        self.assertNotIn("From $10", html)

    def test_cheaper_six_month_tier_does_not_set_the_price(self, _ns, _cs) -> None:
        self._tier("half", 20, months=6)
        self._tier("senior", 35)
        html = self._html()
        self.assertIn(PRICE_35, html)
        self.assertNotIn("From $20", html)

    def test_only_a_six_month_tier_omits_price_line(self, _ns, _cs) -> None:
        self._tier("half", 20, months=6)
        html = self._html()
        self.assertNotIn(
            "From $", html.split('id="membership"')[1].split("</section>")[0]
        )

    def test_no_tiers_omits_price_line(self, _ns, _cs) -> None:
        html = self._html()
        self.assertIn('id="membership"', html)
        self.assertIn("Become a member", html)
        self.assertIn(reverse("membership"), html)
        self.assertNotIn(
            "From $", html.split('id="membership"')[1].split("</section>")[0]
        )

    def test_copy_and_button(self, _ns, _cs) -> None:
        html = self._html()
        self.assertIn("A year of cheaper movie nights, and a hand in keeping the marquee lit.", html)
        self.assertEqual(html.count("btn-member"), 1)
        links = re.findall(r"<a\b[^>]*\bbtn-member\b[^>]*>", html)
        self.assertEqual(len(links), 1)
        self.assertIn(f'href="{reverse("membership")}"', links[0])
        self.assertIn('data-track="membership_cta_click"', links[0])
