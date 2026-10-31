"""Titles and meta descriptions on the section pages.

The 2026-10-15 site audit found four descriptions long enough that Google
cut off the sentence carrying the price or the time. These hold the fix.
"""

import html as html_lib
import json
import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse

# Google shows roughly this many characters of a description on a phone.
DESCRIPTION_LIMIT = 155

SECTION_PAGES = (
    "home",
    "membership",
    "rentals",
    "advertise",
    "heckle_night",
    "open_mic",
    "history",
    "blog_list",
    "vote",
)


def meta_description(html):
    match = re.search(r'<meta name="description" content="([^"]*)"', html)
    return html_lib.unescape(match.group(1)) if match else None


@mock.patch("web.views.get_calendar_month", return_value={})
@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_hero_films", return_value=[])
class TitleAndDescriptionTests(TestCase):
    def test_every_section_description_fits_a_result_snippet(self, *_):
        for name in SECTION_PAGES:
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                description = meta_description(html)
                self.assertTrue(description, "no meta description")
                self.assertLessEqual(
                    len(description),
                    DESCRIPTION_LIMIT,
                    f"{len(description)} chars: {description}",
                )

    def test_history_article_description_matches_its_meta(self, *_):
        # The Article block spells the description out again (block.super
        # can't reach it there), so the two can drift. Hold them together.
        html = self.client.get(reverse("history")).content.decode()
        blocks = [
            json.loads(raw)
            for raw in re.findall(
                r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
            )
        ]
        article = next(b for b in blocks if b.get("@type") == "Article")
        self.assertEqual(article["description"], meta_description(html))
