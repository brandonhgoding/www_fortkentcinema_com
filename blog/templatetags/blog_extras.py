from django import template

register = template.Library()


def _normalize(content):
    return (content or "").replace("\r\n", "\n").replace("\r", "\n")


@register.filter
def excerpt(content, max_length=150):
    text = _normalize(content)
    if not text:
        return ""
    first = text.split("\n\n")[0]
    if len(first) <= max_length:
        return first
    return first[:max_length].strip() + "..."


@register.filter
def paragraphs(content):
    text = _normalize(content)
    if not text:
        return []
    return [p for p in text.split("\n\n") if p.strip()]
