from pathlib import Path

from django.conf import settings
from django.test import TestCase


FONTS_DIR = Path(settings.BASE_DIR) / "dashboard" / "static" / "dashboard" / "fonts"
CSS_DIR = Path(settings.BASE_DIR) / "dashboard" / "static" / "dashboard" / "css"


class FontAssetTests(TestCase):
    def test_fonts_css_exists_and_declares_families(self) -> None:
        css = (CSS_DIR / "fonts.css").read_text()
        self.assertIn("Plus Jakarta Sans", css)
        self.assertIn("Playfair Display", css)
        self.assertIn("Cormorant Garamond", css)
        self.assertIn("@font-face", css)
        # No runtime CDN reference
        self.assertNotIn("fonts.googleapis.com", css)
        self.assertNotIn("fonts.gstatic.com", css)

    def test_woff2_files_present(self) -> None:
        files = list(FONTS_DIR.glob("*.woff2"))
        self.assertGreaterEqual(len(files), 8)  # 4 + 3 + (2-3) weights
