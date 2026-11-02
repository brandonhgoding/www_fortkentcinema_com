"""Titles and meta descriptions on the section pages.

The 2026-10-15 site audit found four descriptions long enough that Google
cut off the sentence carrying the price or the time. These hold the fix.
"""

import html as html_lib
import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse

# Google shows roughly this many characters of a description on a phone.
DESCRIPTION_LIMIT = 155

SECTION_PAGES = (
    "home",
    "rentals",
    "advertise",
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
