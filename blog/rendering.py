"""Render a post's Markdown body to the HTML the public site prints.

Posts were plain text split on blank lines until the dashboard editor
arrived. That format is already valid Markdown — a blank line still starts a
new paragraph — so old posts render the same.

Only staff write posts, but the output is still sanitised against a short
allow-list. A stray `<script>` pasted in from somewhere else should come out
as nothing.
"""

import re
from html import unescape
from xml.etree.ElementTree import Element

import markdown
import nh3
from django.utils.html import strip_tags
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

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


def plain_excerpt(text: str | None, max_length: int = 150) -> str:
    """The first paragraph as plain text, for cards and meta descriptions.

    A leading heading is skipped, since it makes a poor summary, and the
    Markdown syntax is stripped. Without that, `**` and `[links](...)` would
    show up in search results.

    A paragraph with no text left after sanitising (an opening image, a
    linked image, `&nbsp;`, `<br>`) is skipped too.
    """
    html = render_markdown(text)
    if not html:
        return ""
    paragraphs = (
        " ".join(unescape(strip_tags(p)).split())
        for p in re.findall(r"<p>(.*?)</p>", html, re.S)
    )
    first = next(
        (p for p in paragraphs if p),
        " ".join(unescape(strip_tags(html)).split()),
    )
    if len(first) <= max_length:
        return first
    return first[:max_length].strip() + "..."
