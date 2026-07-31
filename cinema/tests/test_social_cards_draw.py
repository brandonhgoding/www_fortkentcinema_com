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


class BackgroundTests(TestCase):
    def test_size_and_mode(self) -> None:
        bg = draw.make_background((300, 200))
        self.assertEqual(bg.size, (300, 200))
        self.assertEqual(bg.mode, "RGBA")

    def test_it_is_a_gradient_not_a_flat_fill(self) -> None:
        bg = draw.make_background((300, 200)).convert("RGB")
        self.assertGreater(len(bg.getcolors(maxcolors=1 << 20) or []), 1)

    def test_it_is_brighter_toward_the_upper_left(self) -> None:
        bg = draw.make_background((300, 200)).convert("RGB")
        self.assertGreater(sum(bg.getpixel((50, 60))), sum(bg.getpixel((290, 195))))


class OrnamentTests(TestCase):
    def _canvas(self) -> Image.Image:
        return Image.new("RGBA", (400, 300), theme.INK + (255,))

    def test_trees_darken_the_bottom_band(self) -> None:
        canvas = self._canvas()
        draw.draw_trees(canvas, band_height=60)
        self.assertLess(
            sum(canvas.convert("RGB").getpixel((0, 299))), sum(theme.INK)
        )

    def test_trees_leave_the_top_alone(self) -> None:
        canvas = self._canvas()
        draw.draw_trees(canvas, band_height=60)
        self.assertEqual(canvas.convert("RGB").getpixel((200, 10)), theme.INK)

    def test_trees_are_deterministic(self) -> None:
        first, second = self._canvas(), self._canvas()
        draw.draw_trees(first, band_height=60)
        draw.draw_trees(second, band_height=60)
        self.assertEqual(first.tobytes(), second.tobytes())

    def test_bulbs_add_gold(self) -> None:
        canvas = self._canvas()
        draw.draw_bulbs(canvas, (200, 20), (200, 280), count=6, radius=6)
        pixels = canvas.convert("RGB").getdata()
        self.assertTrue(any(r > 180 and g > 140 and b < 140 for r, g, b in pixels))

    def test_bulbs_work_horizontally_too(self) -> None:
        canvas = self._canvas()
        before = canvas.tobytes()
        draw.draw_bulbs(canvas, (20, 150), (380, 150), count=6, radius=6)
        self.assertNotEqual(canvas.tobytes(), before)


class CoverCropTests(TestCase):
    def test_output_is_exactly_the_target_size(self) -> None:
        source = Image.new("RGB", (400, 600), (10, 20, 30))
        result = draw.cover_crop(source, 300, 200, 0.5)
        self.assertEqual(result.size, (300, 200))

    def test_top_bias_keeps_the_top_of_the_source(self) -> None:
        source = Image.new("RGB", (100, 400), (0, 0, 0))
        for y in range(200):
            for x in range(100):
                source.putpixel((x, y), (255, 255, 255))
        top_biased = draw.cover_crop(source, 100, 50, 0.0)
        centred = draw.cover_crop(source, 100, 50, 0.5)
        self.assertGreater(
            sum(sum(p) for p in top_biased.getdata()),
            sum(sum(p) for p in centred.getdata()),
        )

    def test_it_upscales_a_small_source(self) -> None:
        source = Image.new("RGB", (50, 50), (10, 20, 30))
        self.assertEqual(draw.cover_crop(source, 400, 300, 0.5).size, (400, 300))


class PanelTests(TestCase):
    def _canvas(self) -> Image.Image:
        return Image.new("RGBA", (400, 300), theme.INK + (255,))

    def test_place_artwork_fills_the_box(self) -> None:
        canvas = self._canvas()
        art = Image.new("RGB", (100, 150), (250, 10, 10))
        draw.place_artwork(canvas, art, (200, 0, 400, 300), 0.5)
        self.assertEqual(canvas.convert("RGB").getpixel((300, 150)), (250, 10, 10))
        self.assertEqual(canvas.convert("RGB").getpixel((10, 150)), theme.INK)

    def test_fade_edge_left_darkens_the_left_of_the_box(self) -> None:
        canvas = self._canvas()
        art = Image.new("RGB", (100, 150), (250, 250, 250))
        draw.place_artwork(canvas, art, (200, 0, 400, 300), 0.5)
        draw.fade_edge(canvas, (200, 0, 400, 300), "left", theme.INK)
        rgb = canvas.convert("RGB")
        self.assertLess(sum(rgb.getpixel((202, 150))), sum(rgb.getpixel((395, 150))))

    def test_fade_edge_bottom_darkens_the_bottom_of_the_box(self) -> None:
        canvas = self._canvas()
        art = Image.new("RGB", (100, 150), (250, 250, 250))
        draw.place_artwork(canvas, art, (0, 0, 400, 200), 0.5)
        draw.fade_edge(canvas, (0, 0, 400, 200), "bottom", theme.INK)
        rgb = canvas.convert("RGB")
        self.assertLess(sum(rgb.getpixel((200, 198))), sum(rgb.getpixel((200, 5))))

    def test_dashed_frame_draws_gold(self) -> None:
        canvas = self._canvas()
        before = canvas.tobytes()
        draw.draw_dashed_frame(canvas, (20, 20, 380, 280), theme.GOLD)
        self.assertNotEqual(canvas.tobytes(), before)

    def test_outlined_badge_draws_text_and_border(self) -> None:
        canvas = self._canvas()
        font = theme.load_font(theme.FONT_MEDIUM, 20)
        draw.draw_outlined_badge(
            canvas, "NOW PLAYING", font, (20, 20), theme.GOLD
        )
        colors = {c for _, c in canvas.convert("RGB").getcolors(maxcolors=1 << 20)}
        self.assertIn(theme.GOLD, colors)
