from django.test import SimpleTestCase

from blog.templatetags.blog_extras import excerpt, paragraphs


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


class ParagraphsTests(SimpleTestCase):
    def test_splits_and_drops_blanks(self):
        self.assertEqual(paragraphs("A.\n\nB.\n\n\n\nC."), ["A.", "B.", "C."])

    def test_empty(self):
        self.assertEqual(paragraphs(""), [])
        self.assertEqual(paragraphs(None), [])
