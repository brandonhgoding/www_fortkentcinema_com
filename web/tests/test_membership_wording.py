"""/membership/ copy that contradicted itself or left the reader guessing.

The audit found the perks section promising popcorn "on your birthday" and
telling members to "show your card", while every tier card said "during your
birthday month" and the FAQ said "tell us your name"; the family tiers never
said who they cover; and nothing said what Join does or what $4 is cheaper
than.
"""

from html import unescape

from audience.models import MembershipTier
from django.test import TestCase
from django.urls import reverse

from web.constants import MEMBERSHIP_FAQ, TICKET_PRICES

HOUSEHOLD = "Covers everyone in your household"


class MembershipWordingTests(TestCase):
    def setUp(self):
        self.html = unescape(self.client.get(reverse("membership")).content.decode())

    def perks_section(self):
        return self.html.split('class="membership-benefits"', 1)[1].split(
            "</section>", 1
        )[0]

    def test_perks_agree_with_the_tier_cards_on_the_birthday(self):
        perks = self.perks_section()
        self.assertIn("birthday month", perks)
        self.assertNotIn("on your birthday", perks)

    def test_perks_say_name_not_card(self):
        perks = self.perks_section()
        self.assertNotIn("Show your card", perks)
        self.assertIn("name", perks)

    def test_family_tiers_say_who_they_cover(self):
        family = MembershipTier.objects.filter(is_family_tier=True)
        self.assertTrue(family.exists())
        self.assertEqual(self.html.count(HOUSEHOLD), family.count())

    def test_joining_is_explained_under_the_tiers(self):
        tiers = self.html.split('id="tiers"', 1)[1].split("</section>", 1)[0]
        self.assertIn("box office", tiers)
        self.assertIn(f"${TICKET_PRICES['adult']}", tiers)
        self.assertIn(f"${TICKET_PRICES['member']}", tiers)


class MembershipFaqWordingTests(TestCase):
    def answer(self, question_start):
        for faq in MEMBERSHIP_FAQ:
            if faq["question"].startswith(question_start):
                return faq["answer"]
        self.fail(f"no FAQ starting {question_start!r}")

    def test_duration_answer_does_not_hedge(self):
        answer = self.answer("How long")
        self.assertNotIn("most are annual", answer)
        self.assertIn("welcome email", answer)
        self.assertNotIn("Ask at the box office", answer)

    def test_family_answer_matches_the_cards(self):
        answer = self.answer("What's included with a family tier")
        self.assertIn("household", answer)
        self.assertNotIn("immediate family", answer)


class NoPrintableCardTests(TestCase):
    """Owner, 2026-10-10: no printable card is promised. Members are looked
    up by name at the box office."""

    def test_membership_page_promises_no_card(self):
        html = self.client.get(reverse("membership")).content.decode().lower()
        for phrase in ("printable", "pdf", "your card", "get a card"):
            self.assertNotIn(phrase, html)

    def test_thanks_page_promises_no_card(self):
        tier = MembershipTier.objects.first()
        html = self.client.get(
            reverse("thanks"), {"tier": tier.slug}
        ).content.decode().lower()
        self.assertNotIn("printable", html)
        self.assertNotIn("pdf", html)
        self.assertIn("give us your name", html)


class JoinOnlineOrAtTheBoxOfficeTests(TestCase):
    """Owner, 2026-10-26: Join buttons are back; the box office stays an
    option in the note and the closing section."""

    def setUp(self):
        self.html = unescape(self.client.get(reverse("membership")).content.decode())

    def test_note_offers_both_ways_to_join(self):
        note = self.html.split('class="membership-tiers__note"', 1)[1].split(
            "</p>", 1)[0]
        self.assertIn("Join online from any tier above, or at the box office "
                      "before any show.", note)

    def test_final_section_sends_people_to_the_tiers(self):
        final = self.html.split('class="membership-page__final-cta"', 1)[1].split(
            "</section>", 1)[0]
        self.assertIn("Pick a tier above and you'll be a member in a minute.", final)
        self.assertIn("box office", final)
        self.assertIn('href="#tiers"', final)
        self.assertIn("Choose a tier", final)

    def test_tiers_section_links_members_to_sign_in(self):
        tiers = self.html.split('class="membership-tiers"', 1)[1].split(
            "</section>", 1)[0]
        self.assertIn("Already a member? ", tiers)
        self.assertIn('href="/login"', tiers)
        self.assertIn("Sign in to see your membership.", tiers)
