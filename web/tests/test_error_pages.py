"""Branded error pages and the trailing-slash forms people actually type.

The audit found /nope rendered Django's bare default: Times on white, no
navigation, no viewport meta. And /movies/<slug>/ and /vote/ — the slashed
forms every other section page uses — landed there. (Both now redirect
home: see test_legacy_redirects.)
"""

from django.template.loader import get_template
from django.test import SimpleTestCase, TestCase

from web.constants import SITE_CONFIG


class NotFoundPageTests(TestCase):
    def setUp(self):
        self.response = self.client.get("/no-such-page-here")
        self.html = self.response.content.decode()

    def test_is_still_a_404(self):
        self.assertEqual(self.response.status_code, 404)

    def test_uses_the_site_chrome(self):
        self.assertTemplateUsed(self.response, "404.html")
        self.assertTemplateUsed(self.response, "base.html")
        self.assertIn("<footer", self.html)

    def test_is_not_indexed(self):
        self.assertIn('content="noindex', self.html)

    def test_offers_somewhere_to_go(self):
        main = self.html.split('<main id="main-content">', 1)[1].split("</main>", 1)[0]
        for href in ("/#now-showing", "/#coming-soon"):
            self.assertIn(f'href="{href}"', main)
        self.assertIn(SITE_CONFIG["cinema"]["phone"], main)


class ServerErrorPageTests(SimpleTestCase):
    """500.html renders with no context processors and no request, so it
    has to stand on its own: no {% url %}, no site_config, no base.html."""

    def test_renders_with_an_empty_context(self):
        """What Django's server_error view gives it."""
        html = get_template("500.html").render({})
        self.assertIn('name="viewport"', html)
        self.assertIn('href="/"', html)
        self.assertIn(SITE_CONFIG["cinema"]["phone"], html)
