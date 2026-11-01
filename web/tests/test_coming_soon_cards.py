"""What a Coming Soon card renders on the server: the members' ribbon and
the trailer opener. The opener's behaviour in a browser is test_e2e's; this
is the markup Alpine is handed, which runs without Chrome."""

import html as html_lib
import re
from unittest import mock

from django.test import TestCase
from django.urls import reverse


def card(**over):
    base = {
        "id": "7", "title": "Wicked", "release_date": "November 22",
        "genre": "", "poster": "w.jpg", "youtube_id": "", "films": [],
        "is_free_for_members": False, "start_date": "2999-11-22",
    }
    base.update(over)
    return base


@mock.patch("web.views.get_hero_films", return_value=[])
class ComingSoonCardTests(TestCase):
    def section(self, *cards):
        with mock.patch("web.views.get_coming_soon", return_value=list(cards)):
            html = self.client.get(reverse("home")).content.decode()
        start = html.index('id="coming-soon"')
        return html[start : html.index("</section>", start)]

    def openers(self, section):
        return re.findall(r'<div\b[^>]*role="button"[^>]*>', section)

    def test_free_run_carries_the_members_ribbon(self, _hero):
        self.assertIn("Free for Members", self.section(card(is_free_for_members=True)))

    def test_paid_run_has_no_ribbon(self, _hero):
        self.assertNotIn("Free for Members", self.section(card()))

    def test_a_run_with_a_trailer_gets_a_keyboard_opener(self, _hero):
        (opener,) = self.openers(self.section(card(youtube_id="yt9")))
        self.assertIn('tabindex="0"', opener)
        self.assertIn('aria-label="Watch Wicked trailer"', opener)
        handler = "trailer = { title: 'Wicked', youtube_id: 'yt9' }"
        for event in ("@click", "@keydown.enter.prevent", "@keydown.space.prevent"):
            with self.subTest(event=event):
                self.assertIn(f'{event}="{handler}"', opener)

    def test_no_trailer_means_no_opener(self, _hero):
        self.assertEqual(self.openers(self.section(card())), [])

    def test_an_apostrophe_in_the_title_cannot_break_the_handler(self, _hero):
        """The title sits inside a single-quoted JS string inside a
        double-quoted attribute. An unescaped ' would end the string and
        Alpine would throw on click."""
        (opener,) = self.openers(
            self.section(card(title="Pan's Labyrinth", youtube_id="yt9"))
        )
        click = html_lib.unescape(re.search(r'@click="([^"]*)"', opener).group(1))
        self.assertEqual(
            click, "trailer = { title: 'Pan\\u0027s Labyrinth', youtube_id: 'yt9' }"
        )
        self.assertIn('aria-label="Watch Pan&#x27;s Labyrinth trailer"', opener)

    def test_a_quote_in_the_title_cannot_break_out_of_the_attribute(self, _hero):
        (opener,) = self.openers(
            self.section(card(title='The "Real" Thing', youtube_id="yt9"))
        )
        click = re.search(r'@click="([^"]*)"', opener)
        self.assertIsNotNone(click, "the double quote ended the attribute early")
        self.assertIn("\\u0022Real\\u0022", click.group(1))
