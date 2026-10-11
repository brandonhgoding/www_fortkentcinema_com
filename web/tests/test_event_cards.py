"""The "Next one" card at the top of each event page.

The audit: none of the three said where the night happens, and Craft
Night's card — alone of the three — gave no price, leaving the reader to
find it in the second section.
"""

import re

from django.test import TestCase
from django.urls import reverse

from web.constants import CRAFT_NIGHT, SITE_CONFIG

STREET = SITE_CONFIG["cinema"]["address"]["street"]


def next_card(html, prefix):
    """From the card's opening tag to the end of the page header it sits in."""
    match = re.search(rf'<div class="{prefix}-next">(.*?)</header>', html, re.S)
    return match.group(1) if match else ""


class EventCardTests(TestCase):
    def card(self, name, prefix):
        html = self.client.get(reverse(name)).content.decode()
        card = next_card(html, prefix)
        self.assertTrue(card, f"no next-one card on {name}")
        return card

    def test_every_card_says_where(self):
        for name, prefix in (
            ("craft_night", "craft"),
            ("heckle_night", "heckle"),
            ("open_mic", "openmic"),
        ):
            with self.subTest(name):
                self.assertIn(STREET, self.card(name, prefix))

    def test_craft_card_gives_the_price(self):
        card = self.card("craft_night", "craft")
        self.assertIn(f"${CRAFT_NIGHT['general_price']}", card)
        self.assertIn(f"${CRAFT_NIGHT['member_price']}", card)
