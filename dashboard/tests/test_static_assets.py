import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase


FONTS_DIR = Path(settings.BASE_DIR) / "dashboard" / "static" / "dashboard" / "fonts"
CSS_DIR = Path(settings.BASE_DIR) / "dashboard" / "static" / "dashboard" / "css"


class FontAssetTests(TestCase):
    def test_fonts_are_self_hosted(self) -> None:
        css = (CSS_DIR / "fonts.css").read_text()
        # No runtime CDN reference
        self.assertNotIn("fonts.googleapis.com", css)
        self.assertNotIn("fonts.gstatic.com", css)

    def test_every_font_file_the_sheet_names_exists(self) -> None:
        css = (CSS_DIR / "fonts.css").read_text()
        urls = re.findall(r"url\(['\"]?([^'\")]+)['\"]?\)", css)
        self.assertTrue(urls)
        for url in urls:
            with self.subTest(url=url):
                self.assertTrue((CSS_DIR / url).resolve().is_file(), url)


TEMPLATES_DIR = Path(settings.BASE_DIR) / "dashboard" / "templates" / "dashboard"


class StyleConsistencyTests(TestCase):
    def test_base_loads_components_sheet(self) -> None:
        base = (TEMPLATES_DIR / "base_dashboard.html").read_text()
        self.assertIn("dashboard/css/components.css", base)


class DrawerFormPatternTests(TestCase):
    """Every drawer form puts its fields in a form with an id, and the
    Cancel and submit buttons in the drawer footer, outside that form."""

    DRAWER_FORMS = sorted(
        p
        for p in TEMPLATES_DIR.glob("_*.html")
        if p.name != "_drawer.html" and 'id="drawer-footer"' in p.read_text()
    )

    def test_footer_cancels_and_submits_its_form(self) -> None:
        for path in self.DRAWER_FORMS:
            html = path.read_text()
            with self.subTest(template=path.name):
                form_id = re.search(r'<form id="([^"]+)"', html)
                self.assertIsNotNone(form_id, "the form needs an id")
                footer = html.split('id="drawer-footer"', 1)[1]
                buttons = re.findall(r"<button [^>]*>", footer)
                self.assertTrue(
                    any("$store.drawer.close()" in b for b in buttons), buttons
                )
                # The submit sits outside the form, so it must name it.
                self.assertTrue(
                    any(
                        'type="submit"' in b and f'form="{form_id.group(1)}"' in b
                        for b in buttons
                    ),
                    buttons,
                )

    def test_no_as_p_inside_the_form(self) -> None:
        # .as_p would skip the {% field %} tag's label and aria wiring.
        for path in self.DRAWER_FORMS:
            body = path.read_text().split('id="drawer-footer"', 1)[0]
            with self.subTest(template=path.name):
                self.assertNotIn(".as_p", body)

    def test_every_label_names_its_control(self) -> None:
        for path in [*self.DRAWER_FORMS, TEMPLATES_DIR / "_field.html"]:
            with self.subTest(template=path.name):
                for label in re.findall(r"<label\b[^>]*>", path.read_text()):
                    self.assertIn("for=", label)
