from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Dict lookup by a variable key in templates: {{ LABELS|get_item:value }}."""
    try:
        return mapping.get(key, key)
    except AttributeError:
        return key
