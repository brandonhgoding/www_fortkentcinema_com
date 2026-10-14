"""The "Next one" card at the top of each event page.

The audit: none of them said where the night happens. (Craft Night, the
third event page, was deleted on 2026-10-13.)
"""

import re

from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG

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
            ("heckle_night", "heckle"),
            ("open_mic", "openmic"),
        ):
            with self.subTest(name):
                self.assertIn(STREET, self.card(name, prefix))

