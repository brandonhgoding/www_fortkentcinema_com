from pathlib import Path

from django.test import TestCase

from cinema.social_cards import theme


class ThemeTests(TestCase):
    def test_font_files_are_present_and_real(self) -> None:
        for path in (theme.FONT_BOLD, theme.FONT_MEDIUM):
            size = Path(path).stat().st_size
            self.assertGreater(size, 10_000, f"{path} looks like an error page")

    def test_licence_ships_with_the_fonts(self) -> None:
        licence = Path(theme.FONT_BOLD).parent / "OFL.txt"
        self.assertIn("SIL OPEN FONT LICENSE", licence.read_text().upper())

    def test_load_font_returns_font_at_requested_size(self) -> None:
        font = theme.load_font(theme.FONT_BOLD, 64)
        self.assertEqual(font.size, 64)

    def test_load_font_is_cached(self) -> None:
        self.assertIs(
            theme.load_font(theme.FONT_BOLD, 48),
            theme.load_font(theme.FONT_BOLD, 48),
        )

    def test_canvas_sizes(self) -> None:
        self.assertEqual(theme.FACEBOOK_SIZE, (1200, 630))
        self.assertEqual(theme.INSTAGRAM_SIZE, (1080, 1080))
