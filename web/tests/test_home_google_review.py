"""The Google review chip on the home hero.

It sits in the line under the hero in both heroes: the film fold and the
empty-week fold. The rating, the review count and the link are
SITE_CONFIG["google_review"], kept by hand like the phone number; None
leaves the line out.
"""

import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG
from web.tests.test_home_hero import HeroBase

REVIEW = {
    "rating": "4.9",
    "count": 112,
    "url": "https://www.google.com/maps/search/?api=1&query=test",
}

CHIP = 'data-track="google_review_click"'


def rating_line(html: str) -> str:
    start = html.index('<p class="hero-members')
    return html[start : html.index("</p>", start)]


@mock.patch.dict(SITE_CONFIG, {"google_review": REVIEW})
@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_hero_films", return_value=[])
class EmptyFoldGoogleReviewTests(TestCase):
    """Nothing booked: the empty-week fold."""

    def _html(self) -> str:
        return self.client.get(reverse("home")).content.decode()

    def test_chip_sits_in_the_rating_line(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        self.assertIn(CHIP, rating_line(self._html()))

    def test_chip_reads_the_rating_count_and_link(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        chip = re.search(rf"<a\b[^>]*{CHIP}[^>]*>.*?</a>", self._html(), re.S).group(0)
        self.assertIn("4.9", chip)
        self.assertIn("112 reviews", chip)
        # Django escapes the & in the query string.
        self.assertIn(
            'href="https://www.google.com/maps/search/?api=1&amp;query=test"', chip
        )
        self.assertIn('target="_blank"', chip)
        self.assertIn('rel="noopener noreferrer"', chip)

    def test_stars_are_hidden_from_screen_readers(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        self.assertIn(
            '<span class="hero-google-stars" aria-hidden="true">', self._html()
        )

    def test_no_config_renders_no_line(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        with mock.patch.dict(SITE_CONFIG, {"google_review": None}):
            self.assertNotIn("hero-members", self._html())

    def test_rating_stays_out_of_the_structured_data(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        # Google forbids marking up your own listing's rating on your own
        # page (self-serving aggregateRating); the chip is for people only.
        self.assertNotIn("aggregateRating", self._html())


@mock.patch.dict(SITE_CONFIG, {"google_review": REVIEW})
class FilmHeroGoogleReviewTests(HeroBase):
    """A showing booked this week: the film fold."""

    def test_chip_sits_once_in_the_rating_line(self) -> None:
        self.booked()
        html = self.home()
        self.assertIn('class="hero hero--film"', html)
        self.assertEqual(html.count(CHIP), 1)
        self.assertIn(CHIP, rating_line(html))
