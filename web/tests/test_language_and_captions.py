"""Language, translation and CC/OC on the home page.

Each shows only when there is something to say: an English run with no
captions looks exactly as it did before these fields existed.
"""

import datetime

from cinema.models import Language, Showtime, Translation
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from web.services.cinema_data import get_now_showing
from web.tests.test_cinema_data import make_engagement, make_film, make_screen


class LanguageCaptionsTests(TestCase):
    def setUp(self) -> None:
        self.screen = make_screen()
        self.film = make_film("Amélie", slug="amelie")
        self.today = timezone.localdate()
        self.eng = make_engagement(
            self.screen, [self.film],
            start=self.today, end=self.today + datetime.timedelta(days=3),
        )
        tomorrow = self.today + datetime.timedelta(days=1)
        self.showtime = Showtime.objects.create(
            engagement=self.eng,
            screen=self.screen,
            starts_at=timezone.make_aware(
                datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day, 19)
            ),
        )

    def _set(self, *, language=Language.ENGLISH, translation=Translation.NONE,
             captions=None) -> None:
        self.eng.language = language
        self.eng.translation = translation
        self.eng.save()
        self.showtime.captions = captions
        self.showtime.save()

    def test_language_label(self) -> None:
        self.assertEqual(self.eng.language_label, "")
        self._set(language=Language.FRENCH)
        self.assertEqual(self.eng.language_label, "French")
        self._set(language=Language.FRENCH, translation=Translation.SUBTITLED)
        self.assertEqual(self.eng.language_label, "French · English subtitles")

    def test_now_showing_carries_label_and_captions(self) -> None:
        self._set(language=Language.FRENCH, translation=Translation.DUBBED,
                  captions="OC")
        movie = get_now_showing()[0]
        self.assertEqual(movie["language_label"], "French · Dubbed in English")
        (times,) = movie["showtimes"].values()
        self.assertEqual(times[0]["captions"], "OC")
        self.assertEqual(times[0]["captions_label"], "Open Captions")

    def test_home_shows_label_and_caption_chip(self) -> None:
        self._set(language=Language.FRENCH, translation=Translation.SUBTITLED,
                  captions="CC")
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('<span class="movie-rating">French · English subtitles</span>', html)
        self.assertIn(
            '<span class="schedule-card__rating">French · English subtitles</span>', html
        )
        # The abbr's tooltip is for the mouse; touch and screen readers get
        # the spelled-out label instead.
        self.assertIn(
            '<abbr class="movie-rating" title="Closed Captions" aria-hidden="true">CC</abbr>'
            '<span class="sr-only">Closed Captions</span>', html
        )
        self.assertIn(
            '<abbr class="schedule-card__rating" title="Closed Captions" aria-hidden="true">CC</abbr>'
            '<span class="sr-only">Closed Captions</span>', html
        )

    def test_home_shows_nothing_extra_for_plain_english(self) -> None:
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Amélie", html)
        self.assertNotIn("<abbr class=", html)
        self.assertNotIn("English subtitles", html)
