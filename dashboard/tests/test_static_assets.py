import re
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


class DesignSystemCssTests(TestCase):
    def test_design_system_sentinels(self) -> None:
        css = (CSS_DIR / "design-system.css").read_text()
        for sentinel in ("--brass:", ".btn-primary", ".status-badge", ".page-header", ".empty-state"):
            self.assertIn(sentinel, css)


TEMPLATES_DIR = Path(settings.BASE_DIR) / "dashboard" / "templates" / "dashboard"


class StyleConsistencyTests(TestCase):
    """Guards against the drift the 2026-10 style audit cleaned up."""

    def test_every_custom_property_used_is_defined(self) -> None:
        # Members, Screens and the engagement detail used var(--stone), which
        # no sheet defined, so their subtitles fell back to body black.
        css = "\n".join(p.read_text() for p in CSS_DIR.glob("*.css"))
        defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
        used = set(re.findall(r"var\((--[a-z0-9-]+)", css))
        self.assertEqual(used - defined, set())

    def test_templates_use_the_shared_button_family(self) -> None:
        # One button family (.btn + variant, design-system.css). These were
        # the page-local copies, each styled differently per page.
        legacy = re.compile(
            r'class="[^"]*\b(primaryButton|secondaryButton|submitButton|'
            r"cancelButton|actionButton|deleteButton|confirmButton|statusPill|"
            r'statusBadge)\b'
        )
        offenders = [
            p.name for p in TEMPLATES_DIR.glob("*.html") if legacy.search(p.read_text())
        ]
        self.assertEqual(offenders, [])

    def test_only_shared_sheets_define_page_chrome(self) -> None:
        # .tableWrapper, .formGroup and .input live in components.css; a page
        # sheet redefining them is how the pages drifted apart.
        for path in CSS_DIR.glob("*.css"):
            if path.name in ("components.css", "design-system.css"):
                continue
            css = path.read_text()
            for selector in (".formGroup", ".input", ".tableWrapper", ".btn", ".page-header"):
                # A top-level rule for the bare class, not a scoped use of it.
                pattern = rf"^{re.escape(selector)}\s*[{{,]"
                self.assertIsNone(
                    re.search(pattern, css, re.M), f"{path.name} redefines {selector}"
                )

    def test_base_loads_components_sheet(self) -> None:
        base = (TEMPLATES_DIR / "base_dashboard.html").read_text()
        self.assertIn("dashboard/css/components.css", base)


class DrawerFormPatternTests(TestCase):
    """Every drawer form follows the one pattern in components.css: fields
    in a .form, then Cancel and the primary action in the drawer footer."""

    DRAWER_FORMS = sorted(
        p
        for p in TEMPLATES_DIR.glob("_*.html")
        if p.name != "_drawer.html" and 'id="drawer-footer"' in p.read_text()
    )

    def test_the_drawer_forms_are_the_ones_we_know(self) -> None:
        # So that a new drawer form is counted, and gets the checks below.
        self.assertEqual(len(self.DRAWER_FORMS), 12, [p.name for p in self.DRAWER_FORMS])

    def test_footer_is_cancel_then_the_primary_submit_for_the_form(self) -> None:
        for path in self.DRAWER_FORMS:
            html = path.read_text()
            with self.subTest(template=path.name):
                form_id = re.search(r'<form id="([^"]+)" class="form"', html)
                self.assertIsNotNone(form_id, 'the form needs an id and class="form"')
                footer = html.split('id="drawer-footer"', 1)[1]
                buttons = re.findall(r"<button [^>]*>", footer)
                self.assertEqual(len(buttons), 2, buttons)
                self.assertIn('class="btn btn-secondary"', buttons[0])
                self.assertIn("$store.drawer.close()", buttons[0])
                self.assertIn('type="submit"', buttons[1])
                self.assertIn(f'form="{form_id.group(1)}"', buttons[1])
                self.assertIn('class="btn btn-primary"', buttons[1])

    def test_no_submit_button_or_as_p_inside_the_form(self) -> None:
        for path in self.DRAWER_FORMS:
            body = path.read_text().split('id="drawer-footer"', 1)[0]
            with self.subTest(template=path.name):
                self.assertNotIn('type="submit"', body)
                self.assertNotIn(".as_p", body)

    def test_every_label_names_its_control(self) -> None:
        for path in [*self.DRAWER_FORMS, TEMPLATES_DIR / "_field.html"]:
            with self.subTest(template=path.name):
                for label in re.findall(r"<label\b[^>]*>", path.read_text()):
                    self.assertIn("for=", label)

    def test_components_sheet_defines_the_pattern(self) -> None:
        css = (CSS_DIR / "components.css").read_text()
        for selector in (
            ".formSection", ".formSectionTitle", ".formIntro", ".formAlert",
            ".fieldOptional", ".fieldHint", "fieldset.formGroup", ".repeatList",
            "[aria-invalid='true']",
        ):
            self.assertIn(selector, css)
