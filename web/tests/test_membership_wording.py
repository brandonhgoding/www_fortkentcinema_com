"""/membership/: what the family tiers cover, what $4 is cheaper than, and
where the closing section and sign-in link point.
"""

from html import unescape

from audience.models import MembershipTier
from django.test import TestCase
from django.urls import reverse

from web.constants import TICKET_PRICES

HOUSEHOLD = "Covers everyone in your household"


class MembershipWordingTests(TestCase):
    def setUp(self):
        self.html = unescape(self.client.get(reverse("membership")).content.decode())

    def test_family_tiers_say_who_they_cover(self):
        family = MembershipTier.objects.filter(is_family_tier=True)
        self.assertTrue(family.exists())
        self.assertEqual(self.html.count(HOUSEHOLD), family.count())

    def test_joining_is_explained_under_the_tiers(self):
        tiers = self.html.split('id="tiers"', 1)[1].split("</section>", 1)[0]
        self.assertIn(f"${TICKET_PRICES['adult']}", tiers)
        self.assertIn(f"${TICKET_PRICES['member']}", tiers)


class JoinOnlineOrAtTheBoxOfficeTests(TestCase):
    """Owner, 2026-10-26: Join buttons are back; the closing section sends
    people to the tiers."""

    def setUp(self):
        self.html = unescape(self.client.get(reverse("membership")).content.decode())

    def test_final_section_sends_people_to_the_tiers(self):
        final = self.html.split('class="membership-page__final-cta"', 1)[1].split(
            "</section>", 1)[0]
        self.assertIn('href="#tiers"', final)
