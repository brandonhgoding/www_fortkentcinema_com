from django import template
from django.utils.safestring import mark_safe

from blog.rendering import (
    plain_excerpt,
    render_body,
    render_markdown,
    truncate_excerpt,
)

register = template.Library()


@register.filter
def excerpt(content, max_length=150):
    return plain_excerpt(content, max_length)


@register.filter
def markdown(content):
    # render_markdown sanitises its output, so it is safe to mark as such.
    return mark_safe(render_markdown(content))


@register.filter
def post_body(post):
    """A post's body in its own format. Both renderers escape or sanitise."""
    return mark_safe(render_body(post.content, post.body_format))


@register.filter
def post_excerpt(post, max_length=150):
    """A post's excerpt in its own format: plain posts keep the old one. Cut
    from BlogPost.lead_text, worked out when the post was saved."""
    return truncate_excerpt(post.lead_text, max_length)
