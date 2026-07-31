import datetime
from io import BytesIO
from unittest import mock

from django.test import TestCase
from PIL import Image

from cinema.models import Engagement, EngagementFilm, Film, Screen
from cinema.social_cards import card_filename, render_card
from cinema.social_cards import layouts
from cinema.social_cards.card import (
    BADGE_COMING_SOON,
    BADGE_NOW_PLAYING,
    FACEBOOK,
    INSTAGRAM,
    CardData,
)

JULY_1 = datetime.date(2026, 7, 1)
JULY_7 = datetime.date(2026, 7, 7)


def a_card(**over: object) -> CardData:
    defaults: dict[str, object] = {
        "badge": BADGE_NOW_PLAYING,
        "headline": "THE SUPER MARIO GALAXY MOVIE",
        "date_line": "NOW THROUGH JULY 7",
        "artwork": (),
        "slug": "the-super-mario-galaxy-movie",
    }
    defaults.update(over)
    return CardData(**defaults)  # type: ignore[arg-type]


def an_image(color: tuple[int, int, int] = (200, 40, 40)) -> Image.Image:
    return Image.new("RGB", (400, 600), color)


def open_png(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


class RenderTests(TestCase):
    def test_facebook_dimensions(self) -> None:
        png = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        self.assertEqual(open_png(png).size, (1200, 630))

    def test_instagram_dimensions(self) -> None:
        png = layouts.render(a_card(), INSTAGRAM, [(an_image(), 0.5)])
        self.assertEqual(open_png(png).size, (1080, 1080))

    def test_output_is_a_png(self) -> None:
        png = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        self.assertEqual(open_png(png).format, "PNG")

    def test_the_canvas_is_actually_drawn_on(self) -> None:
        png = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        colors = open_png(png).convert("RGB").getcolors(maxcolors=1 << 22)
        assert colors is not None
        self.assertGreater(len(colors), 500)

    def test_renders_without_artwork(self) -> None:
        png = layouts.render(a_card(), INSTAGRAM, [])
        self.assertEqual(open_png(png).size, (1080, 1080))

    def test_renders_a_two_panel_split(self) -> None:
        png = layouts.render(
            a_card(), INSTAGRAM,
            [(an_image((250, 10, 10)), 0.5), (an_image((10, 10, 250)), 0.5)],
        )
        image = open_png(png).convert("RGB")
        left = image.getpixel((270, 300))
        right = image.getpixel((810, 300))
        self.assertNotEqual(left, right)

    def test_a_very_long_headline_still_renders(self) -> None:
        png = layouts.render(
            a_card(headline="A" * 120), FACEBOOK, [(an_image(), 0.5)]
        )
        self.assertEqual(open_png(png).size, (1200, 630))

    def test_unknown_platform_raises(self) -> None:
        with self.assertRaises(ValueError):
            layouts.render(a_card(), "tiktok", [])

    def test_rendering_is_deterministic(self) -> None:
        first = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        second = layouts.render(a_card(), FACEBOOK, [(an_image(), 0.5)])
        self.assertEqual(first, second)


class EntryPointTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(
            title="Dune", poster_url="https://image.tmdb.org/t/p/w500/d.jpg"
        )
        self.eng = Engagement.objects.create(
            screen=self.screen, start_date=JULY_1, end_date=JULY_7
        )
        EngagementFilm.objects.create(
            engagement=self.eng, film=self.film, position=1
        )

    def test_render_card_fetches_and_renders(self) -> None:
        with mock.patch(
            "cinema.social_cards.fetch_artwork", return_value=an_image()
        ) as fetch:
            png, filename = render_card(self.eng, FACEBOOK, today=JULY_1)
        fetch.assert_called_once_with("https://image.tmdb.org/t/p/w500/d.jpg")
        self.assertEqual(open_png(png).size, (1200, 630))
        self.assertEqual(filename, "fkc-dune-now-playing-facebook.png")

    def test_render_card_survives_a_failed_fetch(self) -> None:
        with mock.patch("cinema.social_cards.fetch_artwork", return_value=None):
            png, _ = render_card(self.eng, INSTAGRAM, today=JULY_1)
        self.assertEqual(open_png(png).size, (1080, 1080))

    def test_filename_uses_hyphenated_badge(self) -> None:
        data = CardData.from_engagement(self.eng, FACEBOOK, today=JULY_1)
        self.assertEqual(
            card_filename(data, FACEBOOK), "fkc-dune-now-playing-facebook.png"
        )

    def test_filename_for_coming_soon_instagram(self) -> None:
        data = CardData.from_engagement(
            self.eng, INSTAGRAM, badge=BADGE_COMING_SOON, today=JULY_1
        )
        self.assertEqual(
            card_filename(data, INSTAGRAM),
            "fkc-dune-coming-soon-instagram.png",
        )
