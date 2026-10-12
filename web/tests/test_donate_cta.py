"""The home-page donation CTA.

Two things are being protected here, and only one of them is layout.

The first is that a Donate button never points nowhere. The section is
guarded on DONATION["url"], so it shipped ahead of the Square item and
renders nothing until the link exists.

The second is the disclaimer, and it is the reason this file is longer
than the feature. Fort Kent Cinema is a FOR-PROFIT business. Money given
here is not a charitable contribution and is not tax-deductible, so the
page has to say that in as many words rather than leave "donate" to imply
otherwise — and no future tidy-up of the layout may quietly drop it.
"""

from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from web.constants import DONATION

LIVE = {**DONATION, "url": "https://square.link/u/example"}


class DonationHiddenUntilLinkedTests(TestCase):
    """No link, no section. This is the shipped-early state."""

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def test_blank_url_renders_nothing(self, _ns, _cs):
        with mock.patch.dict("web.views.DONATION", {"url": ""}):
            html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("donate-cta", html)
        self.assertNotIn(DONATION["button"], html)

    def test_blanking_the_url_is_still_the_off_switch(self):
        """The guard has to keep working now that a real link is in.

        A paused or replaced Square item should be a one-line edit rather
        than a revert, so the empty-string case stays tested after the
        constant went live.
        """
        with mock.patch.dict("web.views.DONATION", {"url": ""}):
            with mock.patch("web.views.get_now_showing", return_value=[]):
                with mock.patch("web.views.get_coming_soon", return_value=[]):
                    html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("donate-cta", html)


class SquareLinkTests(TestCase):
    """The live link, checked for the ways a pasted URL goes wrong."""

    def test_it_is_a_square_link(self):
        self.assertTrue(
            DONATION["url"].startswith("https://square.link/u/"),
            DONATION["url"],
        )

    def test_it_is_https(self):
        """A payment link downgraded to http is a payment link in clear."""
        self.assertTrue(DONATION["url"].startswith("https://"))

    def test_it_carries_no_query_string(self):
        """Square link ids are path segments. A `?` here usually means a
        tracking parameter got pasted along with the URL."""
        self.assertNotIn("?", DONATION["url"])


class DonationLiveTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def setUp(self, _ns, _cs):
        with mock.patch.dict("web.views.DONATION", LIVE):
            self.html = self.client.get(reverse("home")).content.decode()

    def test_the_section_appears_once_the_url_is_set(self):
        self.assertIn("donate-cta", self.html)

    def test_the_link_says_donate(self):
        self.assertIn(">Donate &rarr;</a>", self.html)

    def test_the_button_points_at_the_configured_link(self):
        self.assertIn(f'href="{LIVE["url"]}"', self.html)

    def test_the_link_opens_safely_in_a_new_tab(self):
        """An external payment link leaving window.opener reachable is the
        one thing a target=_blank must not do."""
        self.assertIn('rel="noopener noreferrer"', self.html)

    def test_the_new_window_is_announced_to_screen_readers(self):
        self.assertIn("(opens in new window)", self.html)

    def test_it_is_tracked_like_the_other_home_ctas(self):
        self.assertIn('data-track="donate_click"', self.html)

    def test_it_sits_in_support_beside_the_sponsor_link(self):
        """Both asks live in the one slim Support strip at the foot of the
        page, as quiet text links rather than two competing bands."""
        support = self.html[self.html.index('id="support"') :]
        self.assertIn("sponsor-cta", support)
        self.assertGreater(support.index("donate-cta"), support.index("sponsor-cta"))

    def test_it_is_a_text_link_not_a_button(self):
        donate = self.html[self.html.index("donate-cta") :]
        donate = donate[: donate.index("</a>")]
        self.assertIn("home-link", donate)
        self.assertNotIn("btn-ticket", donate)


class DisclaimerTests(TestCase):
    """The part that is not allowed to quietly disappear."""

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_now_showing", return_value=[])
    def setUp(self, _ns, _cs):
        with mock.patch.dict("web.views.DONATION", LIVE):
            self.html = self.client.get(reverse("home")).content.decode()

    def test_the_disclaimer_is_on_the_page(self):
        self.assertIn(escape(DONATION["disclaimer"]), self.html)

    def test_it_says_the_money_is_not_tax_deductible(self):
        self.assertIn("isn't tax-deductible", DONATION["disclaimer"])

    def test_it_sits_after_the_link_not_before(self):
        """The last thing read before the click."""
        self.assertGreater(
            self.html.index("donate-cta__disclaimer"),
            self.html.index('data-track="donate_click"'),
        )

    def test_nothing_here_claims_charitable_status(self):
        """A for-profit business may not imply a deduction it cannot give.

        Checked across every string in the constant, so a later edit to
        the body or the title cannot reintroduce the claim the disclaimer
        exists to rule out.
        """
        copy = " ".join(v for v in DONATION.values() if isinstance(v, str)).lower()
        for claim in (
            "non-profit",
            "nonprofit",
            "501(c)(3)",
            "501c3",
            "charitable",
            "tax deductible",
            "write-off",
        ):
            self.assertNotIn(claim, copy, claim)

    def test_the_only_deductibility_language_is_the_denial(self):
        copy = " ".join(v for v in DONATION.values() if isinstance(v, str)).lower()
        self.assertEqual(copy.count("tax-deductible"), 1)
        self.assertIn("isn't tax-deductible", copy)
