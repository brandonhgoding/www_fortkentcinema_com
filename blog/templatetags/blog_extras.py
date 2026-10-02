from django import template
from django.utils.safestring import mark_safe

from blog.rendering import plain_excerpt, render_markdown

register = template.Library()


@register.filter
def excerpt(content, max_length=150):
    return plain_excerpt(content, max_length)


@register.filter
def markdown(content):
    # render_markdown sanitises its output, so it is safe to mark as such.
    return mark_safe(render_markdown(content))
