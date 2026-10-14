"""The smaller findings from the 2026-10-13 home page audit.

Each is low impact on its own: things a screen reader announces wrongly or
not at all, a section that is blank without JavaScript, and metadata that
carried no fact worth quoting.
"""

import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG, TICKET_PRICES
from web.tests.test_home_sections import movie
from web.tests.test_movie_pages import MoviePageFixture


@mock.patch("web.views.get_coming_soon", return_value=[movie(id="2", title="Alpha")])
@mock.patch("web.views.get_now_showing", return_value=[movie()])
class HomeMarkupTests(TestCase):
    def home(self):
        return self.client.get(reverse("home")).content.decode()

    def test_day_switcher_is_a_labelled_group_that_announces_the_day(self, *_):
        html = self.home()
        self.assertRegex(
            html, r'<div class="date-nav" role="group" aria-label="Choose a day">'
        )
        self.assertRegex(
            html, r'<span class="date-nav__current"[^>]*aria-live="polite"'
        )

    def test_film_cards_show_without_javascript(self, *_):
        """Alpine strips x-cloak; with no JavaScript nothing does, and every
        card stayed display:none. The overlay must stay hidden all the same."""
        noscript = re.search(r"<noscript>(.*?)</noscript>", self.home(), re.S)
        self.assertIsNotNone(noscript)
        self.assertIn("#now-showing .movie-card[x-cloak]", noscript.group(1))
        self.assertNotIn("overlay", noscript.group(1))

    def test_view_toggle_says_which_view_is_on(self, *_):
        html = self.home()
        self.assertIn(""":aria-pressed="view === 'grid'\"""", html)
        self.assertIn(""":aria-pressed="view === 'calendar'\"""", html)

    def test_headings_are_not_uppercase_in_the_markup(self, *_):
        """Some screen readers spell all-caps words letter by letter, and
        search snippets reuse the source text. CSS does the capitals."""
        html = self.home()
        self.assertIn(f'<h1 class="marquee-title">{SITE_CONFIG["cinema"]["name"]}</h1>', html)
        self.assertIn(SITE_CONFIG["cinema"]["tagline"].replace("'", "&#x27;"), html)
        self.assertIn('<h2 class="section-title">Now Showing</h2>', html)
        self.assertIn('<h2 class="section-title">Coming Soon</h2>', html)

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
        self.assertIn('<h2 class="footer-heading"', footer)


class CssCapitalsTests(TestCase):
    def test_marquee_capitals_come_from_css(self):
        bundle = Path(settings.BASE_DIR) / "static" / "css" / "bundle.css"
        if not bundle.exists():
            self.skipTest("bundle.css not built")
        css = bundle.read_text()
        for selector in (".marquee-title", ".marquee-subtitle"):
            rules = re.findall(re.escape(selector) + r"\{([^}]*)\}", css)
            self.assertTrue(
                any("text-transform:uppercase" in r for r in rules),
                f"{selector} has no text-transform:uppercase",
            )


class SharedImageOnOtherPagesTests(MoviePageFixture):
    def test_a_poster_is_not_given_the_default_image_size(self):
        """A film page shares its poster; its size isn't 1200x630, so the
        default image's width and height must not ride along."""
        html = self.client.get(f"/movies/{self.showing.slug}").content.decode()
        self.assertNotIn("og:image:width", html)
        self.assertIn(
            f'<meta property="og:image:alt" content="Poster for {self.showing.title}" />',
            html,
        )

    def test_history_describes_its_own_image(self):
        for path, words in (("/history/", "Savoy"),):
            with self.subTest(path=path):
                html = self.client.get(path).content.decode()
                alt = re.search(r'<meta property="og:image:alt" content="([^"]*)"', html)
                self.assertIn(words, alt.group(1))
