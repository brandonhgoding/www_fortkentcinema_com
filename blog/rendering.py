"""Render a post's body to the HTML the public site prints.

A post's body is in one of two formats (BlogPost.body_format):

- plain: posts from before the dashboard editor. Plain text, one paragraph
  per blank line, autoescaped, exactly as the old template loop printed it.
  It is not Markdown: parsed as Markdown, a line opening with '#' became a
  heading, "1986." started a list, and "<favorite snack>" was dropped.
- markdown: everything written in the editor since.

Only staff write posts, but Markdown output is still sanitised against a
short allow-list. A stray `<script>` pasted in from somewhere else should come
out as nothing.
"""

import re
from html import unescape
from xml.etree.ElementTree import Element

import markdown
import nh3
from django.utils.html import escape, strip_tags
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

PLAIN = "plain"
MARKDOWN = "markdown"

ALLOWED_TAGS = {
    "p", "br", "strong", "em", "a", "ul", "ol", "li", "blockquote",
    "h2", "h3", "h4", "h5", "h6", "hr", "code", "pre",
}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}, "ol": {"start"}}


class _DemoteHeadings(Treeprocessor):
    """`#` becomes <h2>, `##` <h3>, and so on.

    The post title is the page's only <h1>, so a writer's top-level heading has
    to sit below it in the outline.
    """

    def run(self, root: Element) -> None:
        for el in root.iter():
            if re.fullmatch(r"h[1-5]", el.tag):
                el.tag = f"h{int(el.tag[1]) + 1}"


class _DemoteHeadingsExtension(Extension):
    def extendMarkdown(self, md):
        md.treeprocessors.register(_DemoteHeadings(md), "demote_headings", 5)


def _normalize(text: str | None) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def render_markdown(text: str | None) -> str:
    html = markdown.markdown(
        _normalize(text),
        extensions=["sane_lists", "smarty", _DemoteHeadingsExtension()],
    )
    return nh3.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)


def plain_paragraphs(text: str | None) -> list[str]:
    """A plain-text body's paragraphs: split on blank lines, blanks dropped."""
    return [p for p in _normalize(text).split("\n\n") if p.strip()]


def render_plain(text: str | None) -> str:
    """The pre-Markdown body: `<p>` per paragraph, autoescaped, no separators.
    Byte for byte what `{% for para in post.content|paragraphs %}<p>{{ para }}</p>{% endfor %}`
    printed."""
    return "".join(f"<p>{escape(p)}</p>" for p in plain_paragraphs(text))


def render_body(text: str | None, body_format: str) -> str:
    if body_format == PLAIN:
        return render_plain(text)
    return render_markdown(text)


def first_paragraph(text: str | None, body_format: str) -> str:
    """The text a card or meta description is cut from, before truncation.

    Plain: the first blank-line paragraph, as typed, which is what cards
    always showed for those posts.

    Markdown: the first paragraph with any text in it, as plain text. A
    leading heading is skipped, since it makes a poor summary, and the
    Markdown syntax is stripped. Without that, `**` and `[links](...)` would
    show up in search results. A paragraph with no text left after
    sanitising (an opening image, a linked image, `&nbsp;`, `<br>`) is
    skipped too.
    """
    if body_format == PLAIN:
        return _normalize(text).split("\n\n")[0]
    html = render_markdown(text)
    if not html:
        return ""
    paragraphs = (
        " ".join(unescape(strip_tags(p)).split())
        for p in re.findall(r"<p>(.*?)</p>", html, re.S)
    )
    return next(
        (p for p in paragraphs if p),
        " ".join(unescape(strip_tags(html)).split()),
    )


def truncate_excerpt(first: str, max_length: int = 150) -> str:
    if len(first) <= max_length:
        return first
    return first[:max_length].strip() + "..."


def plain_excerpt(text: str | None, max_length: int = 150) -> str:
    """A Markdown body's first paragraph as plain text, for cards and meta
    descriptions. See first_paragraph."""
    return truncate_excerpt(first_paragraph(text, MARKDOWN), max_length)
