"""Render the Thursday email's two bodies from a build_context() dict."""

from django.template.loader import render_to_string


def render_issue(context: dict) -> tuple[str, str]:
    """(html, text) for one issue. Both carry the literal {unsubscribe_url}
    placeholder from the context; the sender substitutes per recipient."""
    html = render_to_string("newsletter/email/issue.html", context)
    text = render_to_string("newsletter/email/issue.txt", context)
    return html, text
