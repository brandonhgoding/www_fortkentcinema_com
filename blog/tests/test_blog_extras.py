from django.test import SimpleTestCase

from blog.rendering import render_markdown
from blog.templatetags.blog_extras import excerpt, markdown


class ExcerptTests(SimpleTestCase):
    def test_first_paragraph_short(self):
        self.assertEqual(excerpt("Hello world.\n\nSecond para."), "Hello world.")

    def test_truncates_long_first_paragraph(self):
        text = "x" * 200
        out = excerpt(text, 150)
        self.assertTrue(out.endswith("..."))
        self.assertEqual(len(out), 153)

    def test_normalizes_crlf(self):
        self.assertEqual(excerpt("A.\r\n\r\nB."), "A.")

    def test_empty(self):
        self.assertEqual(excerpt(""), "")
        self.assertEqual(excerpt(None), "")

    def test_strips_markdown_syntax(self):
        """Cards and meta descriptions are plain text. Raw `**` or `[..](..)`
        there would also show up in search results."""
        self.assertEqual(
            excerpt("A **bold** take on [Dune](https://example.com)."),
            "A bold take on Dune.",
        )

    def test_skips_a_leading_heading(self):
        self.assertEqual(excerpt("# Verdict\n\nGo see it."), "Go see it.")

    def test_skips_paragraphs_the_sanitiser_emptied(self):
        """An opening image (linked or not), `&nbsp;` or `<br>` leaves an
        empty <p> behind. The card showed nothing at all."""
        for body in (
            "![poster](/media/a.png)\n\nGo see it.",
            "[![poster](/media/a.png)](https://x.test)\n\nGo see it.",
            "&nbsp;\n\nGo see it.",
            "<br>\n\nGo see it.",
        ):
            with self.subTest(body=body):
                self.assertEqual(excerpt(body), "Go see it.")

    def test_joins_soft_wrapped_lines(self):
        self.assertEqual(excerpt("One line\nwrapped here."), "One line wrapped here.")


class MarkdownTests(SimpleTestCase):
    def test_blank_lines_start_paragraphs(self):
        """Posts from before the editor are body_format=plain and never reach
        this renderer; see test_body_format."""
        html = render_markdown("First para.\n\nSecond para.\n\n\n\nThird.")
        self.assertEqual(html.count("<p>"), 3)
        self.assertIn("<p>First para.</p>", html)

    def test_inline_formatting_and_links(self):
        html = render_markdown("**bold** *it* [l](https://x.test)")
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<em>it</em>", html)
        self.assertIn('href="https://x.test"', html)

    def test_headings_sit_below_the_post_title(self):
        html = render_markdown("# Top\n\n## Next")
        self.assertIn("<h2>Top</h2>", html)
        self.assertIn("<h3>Next</h3>", html)
        self.assertNotIn("<h1", html)

    def test_scripts_and_handlers_are_stripped(self):
        html = render_markdown(
            '<script>alert(1)</script>\n\n<a href="javascript:alert(1)" onclick="x()">x</a>'
            "\n\n<img src=x onerror=alert(1)>"
        )
        self.assertNotIn("<script", html)
        self.assertNotIn("alert(1)</", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("onclick", html)
        self.assertNotIn("<img", html)

    def test_numbered_list_keeps_its_start(self):
        """A list continued after a paragraph ("3. ...") must not restart at 1."""
        html = render_markdown("3. Third\n4. Fourth")
        self.assertIn('<ol start="3">', html)

    def test_filter_marks_output_safe(self):
        self.assertIn("<p>hi</p>", str(markdown("hi")))

    def test_empty(self):
        self.assertEqual(render_markdown(None), "")
