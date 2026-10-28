"""The Google review chip on the home hero.

It hangs to the right of the member sentence, on the same line, in both
heroes: the film fold and the bulb marquee. The rating, the review count
and the link are SITE_CONFIG["google_review"], kept by hand like the phone
number; None leaves the chip out and the member sentence stands alone.
"""

import datetime
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from audience.models import Member, MembershipTerm, MembershipTier

from web.constants import SITE_CONFIG
from web.tests.test_home_hero import HeroBase

SQUARE_ON = {
    "SQUARE_ACCESS_TOKEN": "t",
    "SQUARE_LOCATION_ID": "L",
    "SQUARE_TICKET_CATEGORY_ID": "C",
}

REVIEW = {
    "rating": "4.9",
    "count": 112,
    "url": "https://www.google.com/maps/search/?api=1&query=test",
}


def one_member() -> None:
    tier = MembershipTier.objects.get(slug="individual")
    member = Member.objects.create(first_name="A", last_name="B", email="a@b.c")
    MembershipTerm.objects.create(
        member=member,
        tier=tier,
        started_on=timezone.localdate(),
        expires_on=timezone.localdate() + datetime.timedelta(days=30),
        price_paid=Decimal("60.00"),
    )


@mock.patch.dict(SITE_CONFIG, {"google_review": REVIEW})
@mock.patch("web.views.get_coming_soon", return_value=[])
@mock.patch("web.views.get_now_showing", return_value=[])
class MarqueeGoogleReviewTests(TestCase):
    """Nothing booked: the marquee hero."""

    def _html(self) -> str:
        return self.client.get(reverse("home")).content.decode()

    def test_chip_sits_in_the_member_line_to_the_right(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        one_member()
        html = self._html()
        line_start = html.index('<p class="hero-members">')
        line_end = html.index("</p>", line_start)
        line = html[line_start:line_end]
        self.assertIn("to keep the lights on", line)
        self.assertIn('class="hero-google"', line)
        self.assertLess(line.index("lights on"), line.index("hero-google"))

    def test_chip_reads_the_rating_count_and_link(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        one_member()
        html = self._html()
        self.assertIn('<span class="hero-google-rating">4.9</span>', html)
        self.assertIn("on Google", html)
        self.assertIn("112 reviews", html)
        # Django escapes the & in the query string.
        self.assertIn(
            '<a class="hero-google" href="https://www.google.com/maps/search/'
            '?api=1&amp;query=test" target="_blank" rel="noopener noreferrer"',
            html,
        )

    def test_stars_are_hidden_from_screen_readers(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        one_member()
        self.assertIn(
            '<span class="hero-google-stars" aria-hidden="true">', self._html()
        )

    def test_chip_stands_alone_with_no_members(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        html = self._html()
        self.assertIn('class="hero-google"', html)
        self.assertNotIn("hero-members-count", html)
        self.assertNotIn("lights on", html)

    def test_no_config_leaves_the_sentence_alone(
        self, _ns: mock.Mock, _cs: mock.Mock
    ) -> None:
        one_member()
        with mock.patch.dict(SITE_CONFIG, {"google_review": None}):
            html = self._html()
        self.assertNotIn("hero-google", html)
        self.assertIn("to keep the lights on", html)

    def test_no_config_and_no_members_renders_no_line(
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


@override_settings(**SQUARE_ON)
@mock.patch.dict(SITE_CONFIG, {"google_review": REVIEW})
class FilmHeroGoogleReviewTests(HeroBase):
    """A showing booked this week: the film fold."""

    def test_chip_sits_once_in_the_member_line_over_the_lockup(self) -> None:
        self.booked()
        one_member()
        html = self.home()
        self.assertIn('class="hero hero--film"', html)
        self.assertEqual(html.count('class="hero-google"'), 1)
        line = html.index('class="hero-members hero-film__members"')
        chip = html.index('class="hero-google"')
        self.assertLess(line, chip)
        self.assertLess(html.index("lights on"), chip)
        self.assertLess(chip, html.index('<h1 class="hero-film__lockup">'))
