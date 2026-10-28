"""Language, translation and CC/OC on the home page.

Each shows only when there is something to say: an English run with no
captions looks exactly as it did before these fields existed.
"""

import datetime

from cinema.models import Language, Showtime, Translation
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from web.services.cinema_data import get_hero_films
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

    def test_hero_film_carries_label_and_captions(self) -> None:
        self._set(language=Language.FRENCH, translation=Translation.DUBBED,
                  captions="OC")
        movie = get_hero_films()[0]
        self.assertEqual(movie["language_label"], "French · Dubbed in English")
        (slot,) = movie["upcoming"]
        times = slot["times"]
        self.assertEqual(times[0]["captions"], "OC")
        self.assertEqual(times[0]["captions_label"], "Open Captions")
        self.assertEqual(
            times[0]["captions_note"],
            "This showing will be played with open captions.",
        )

    def test_closed_captions_carry_no_note(self) -> None:
        self._set(captions="CC")
        (slot,) = get_hero_films()[0]["upcoming"]
        self.assertEqual(slot["times"][0]["captions_note"], "")

    def test_home_shows_open_captions_chip_and_sentence(self) -> None:
        # The OC chip sits beside the time, as CC does, so the row of times
        # still scans as a row; the sentence under it says what the chip
        # means, so nobody at the box office is asked. The hero's row of
        # times is the listing, and it wears the hero's rating chip.
        self._set(captions="OC")
        html = self.client.get(reverse("home")).content.decode()
        note = (
            '<span class="showtime__note">'
            "This showing will be played with open captions.</span>"
        )
        self.assertEqual(html.count(note), 1)
        self.assertIn(
            '<span class="showtime showtime--noted">7:00 PM '
            '<abbr class="hero-film__cert" title="Open Captions" aria-hidden="true">'
            "OC</abbr>" + note,
            html,
        )
        # The sentence is the spoken label; a second sr-only "Open Captions"
        # would read it twice.
        self.assertNotIn('<span class="sr-only">Open Captions</span>', html)

    def test_home_shows_label_and_caption_chip(self) -> None:
        self._set(language=Language.FRENCH, translation=Translation.SUBTITLED,
                  captions="CC")
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('<span class="hero-film__lang">French · English subtitles</span>', html)
        # The abbr's tooltip is for the mouse; touch and screen readers get
        # the spelled-out label instead.
        self.assertIn(
            '<abbr class="hero-film__cert" title="Closed Captions" aria-hidden="true">CC</abbr>'
            '<span class="sr-only">Closed Captions</span>', html
        )

    def test_home_shows_nothing_extra_for_plain_english(self) -> None:
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("Amélie", html)
        self.assertNotIn("<abbr class=", html)
        self.assertNotIn("English subtitles", html)


class RatingChipTests(TestCase):
    """The rating chip shows only when the film has a rating.

    Many classics and local films carry none; an empty chip rendered as a
    bare outlined box beside the runtime.
    """

    def _home(self, rating: str) -> str:
        screen = make_screen()
        film = make_film("Nosferatu", slug="nosferatu", rating=rating)
        today = timezone.localdate()
        eng = make_engagement(
            screen, [film], start=today, end=today + datetime.timedelta(days=3)
        )
        tomorrow = today + datetime.timedelta(days=1)
        Showtime.objects.create(
            engagement=eng, screen=screen,
            starts_at=timezone.make_aware(
                datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day, 19)
            ),
        )
        return self.client.get(reverse("home")).content.decode()

    def test_rated_film_shows_the_chip(self) -> None:
        self.assertIn('<span class="hero-film__cert">PG-13</span>', self._home("PG-13"))

    def test_unrated_film_has_no_empty_chip(self) -> None:
        html = self._home("")
        self.assertNotIn('<span class="hero-film__cert"></span>', html)
