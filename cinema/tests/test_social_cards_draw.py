from django.test import TestCase
from PIL import Image

from cinema.social_cards import draw, theme


class WrapTests(TestCase):
    def setUp(self) -> None:
        self.font = theme.load_font(theme.FONT_BOLD, 40)

    def test_empty_text_wraps_to_nothing(self) -> None:
        self.assertEqual(draw.wrap_lines("", self.font, 500), [])

    def test_short_text_stays_on_one_line(self) -> None:
        self.assertEqual(draw.wrap_lines("DUNE", self.font, 500), ["DUNE"])

    def test_long_text_wraps(self) -> None:
        lines = draw.wrap_lines(
            "THE SUPER MARIO GALAXY MOVIE", self.font, 400
        )
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(self.font.getlength(line), 400)

    def test_a_single_unbreakable_word_is_kept_whole(self) -> None:
        self.assertEqual(
            draw.wrap_lines("SUPERCALIFRAGILISTIC", self.font, 50),
            ["SUPERCALIFRAGILISTIC"],
        )


class FitTextTests(TestCase):
    def test_short_headline_uses_the_maximum_size(self) -> None:
        lines, font = draw.fit_text(
            "DUNE", theme.FONT_BOLD, 640, 250, max_size=92, min_size=44
        )
        self.assertEqual(lines, ["DUNE"])
        self.assertEqual(font.size, 92)

    def test_long_headline_shrinks(self) -> None:
        _, font = draw.fit_text(
            "THE LORD OF THE RINGS THE RETURN OF THE KING EXTENDED EDITION",
            theme.FONT_BOLD,
            640,
            250,
            max_size=92,
            min_size=44,
        )
        self.assertLess(font.size, 92)

    def test_it_never_shrinks_below_the_floor(self) -> None:
        _, font = draw.fit_text(
            " ".join(["VERYLONGWORD"] * 40),
            theme.FONT_BOLD,
            640,
            250,
            max_size=92,
            min_size=44,
        )
        self.assertEqual(font.size, 44)

    def test_fitted_block_fits_the_box(self) -> None:
        lines, font = draw.fit_text(
            "THE SUPER MARIO GALAXY MOVIE",
            theme.FONT_BOLD,
            640,
            250,
            max_size=92,
            min_size=44,
        )
        height = len(lines) * draw.line_height(font, 0.98)
        self.assertLessEqual(height, 250)
        for line in lines:
            self.assertLessEqual(font.getlength(line), 640)


class GlowTextTests(TestCase):
    def _canvas(self) -> Image.Image:
        return Image.new("RGBA", (600, 300), theme.INK + (255,))

    def test_it_draws_something(self) -> None:
        canvas = self._canvas()
        before = canvas.tobytes()
        font = theme.load_font(theme.FONT_BOLD, 48)
        draw.draw_glow_text(
            canvas, ["DUNE"], font, (20, 20), 0.98, theme.CREAM, theme.GOLD
        )
        self.assertNotEqual(canvas.tobytes(), before)

    def test_it_returns_the_baseline_below_the_block(self) -> None:
        canvas = self._canvas()
        font = theme.load_font(theme.FONT_BOLD, 48)
        bottom = draw.draw_glow_text(
            canvas, ["ONE", "TWO"], font, (20, 20), 0.98,
            theme.CREAM, theme.GOLD,
        )
        self.assertEqual(bottom, 20 + 2 * draw.line_height(font, 0.98))

    def test_last_line_is_gold_when_the_headline_wraps(self) -> None:
        canvas = self._canvas()
        font = theme.load_font(theme.FONT_BOLD, 60)
        draw.draw_glow_text(
            canvas, ["AAAA", "BBBB"], font, (20, 20), 0.98,
            theme.CREAM, theme.GOLD,
        )
        colors = {c for _, c in canvas.convert("RGB").getcolors(maxcolors=1 << 20)}
        self.assertIn(theme.GOLD, colors)
        self.assertIn(theme.CREAM, colors)

    def test_single_line_headline_has_no_gold_glyphs(self) -> None:
        canvas = self._canvas()
        font = theme.load_font(theme.FONT_BOLD, 60)
        draw.draw_glow_text(
            canvas, ["AAAA"], font, (20, 20), 0.98, theme.CREAM, theme.GOLD
        )
        colors = {c for _, c in canvas.convert("RGB").getcolors(maxcolors=1 << 20)}
        self.assertIn(theme.CREAM, colors)
        self.assertNotIn(theme.GOLD, colors)
