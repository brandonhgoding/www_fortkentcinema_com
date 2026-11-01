"""The smaller findings from the 2026-10-13 home page audit.

Each is low impact on its own: things a screen reader announces wrongly or
not at all, a section that is blank without JavaScript, and metadata that
carried no fact worth quoting.
"""

import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG, TICKET_PRICES
from web.tests.test_home_sections import hero_film, movie


@mock.patch("web.views.get_coming_soon", return_value=[movie(id="2", title="Alpha")])
@mock.patch("web.views.get_hero_films", return_value=[hero_film()])
class HomeMarkupTests(TestCase):
    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def test_view_toggle_says_which_view_is_on(self, *_):
        html = self.home()
        self.assertIn(""":aria-pressed="view === 'grid'\"""", html)
        self.assertIn(""":aria-pressed="view === 'calendar'\"""", html)

    def test_headings_are_not_uppercase_in_the_markup(self, *_):
        """Some screen readers spell all-caps words letter by letter, and
        search snippets reuse the source text. CSS does the capitals."""
        html = self.home()
        name = SITE_CONFIG["cinema"]["name"]
        h1 = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.S).group(1)
        self.assertIn(name, h1)
        self.assertNotIn(name.upper(), h1)
        self.assertNotIn("COMING SOON", html)

    def test_meta_description_carries_quotable_facts(self, *_):
        with mock.patch.dict(TICKET_PRICES, adult=9, member=3):
            html = self.home()
        description = re.search(r'<meta name="description" content="([^"]*)"', html)
        og = re.search(r'<meta property="og:description" content="([^"]*)"', html)
        for content in (description.group(1), og.group(1)):
            self.assertIn(SITE_CONFIG["cinema"]["address"]["street"], content)
            self.assertIn("$9", content)
            self.assertIn("$3", content)
        self.assertLessEqual(len(description.group(1)), 160)

    def test_share_image_has_size_and_alt(self, *_):
        html = self.home()
        self.assertIn('<meta property="og:image:width" content="1200" />', html)
        self.assertIn('<meta property="og:image:height" content="630" />', html)
        self.assertRegex(html, r'<meta property="og:image:alt" content="[^"]{10,}" />')

    def test_footer_headings_are_h2(self, *_):
        footer = self.home().split('<footer class="footer">', 1)[1]
        self.assertNotIn("<h3", footer)
        self.assertIn("<h2", footer)
