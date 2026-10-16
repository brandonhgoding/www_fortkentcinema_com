"""Titles and meta descriptions on the section pages.

The 2026-10-15 site audit found the membership page titled
"Membership — Fort Kent Cinema" under an H1 and nav button that say
"Become a Member" (the sitelink rule: label = title = H1), and four
descriptions long enough that Google cut off the sentence carrying the
price or the time. These hold the fixes.
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
@mock.patch("web.views.get_now_showing", return_value=[])
class TitleAndDescriptionTests(TestCase):
    def test_membership_title_is_the_sitelink_label(self, *_):
        # Nav button, <title>, og:title and <h1> all read the same, as on
        # the Buy Ad Space and Rent the Cinema pages.
        html = self.client.get(reverse("membership")).content.decode()
        self.assertIn("<title>Become a Member | Fort Kent Cinema</title>", html)
        self.assertIn(
            '<meta property="og:title" content="Become a Member | Fort Kent Cinema"',
            html,
        )
        self.assertNotIn("Membership — Fort Kent Cinema", html)

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
