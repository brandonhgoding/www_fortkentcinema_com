from django import forms, template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Dict lookup by a variable key in templates: {{ LABELS|get_item:value }}."""
    try:
        return mapping.get(key, key)
    except AttributeError:
        return key


@register.inclusion_tag("dashboard/_field.html")
def field(bound_field, label=None, hint=None, optional=None):
    """One form field in the shared drawer-form pattern (components.css).

    Renders a .formGroup: the label (with an "optional" marker on a field
    that is not required), the control, its error and its hint. A checkbox
    renders as a .checkboxLabel row instead.

    `label` and `hint` override the form's own label and help_text; pass
    hint="" to hide a help_text written for the admin.

    The hint and error take Django's own ids (<id>_helptext, <id>_error), so
    the aria-describedby and aria-invalid Django puts on the control point
    at them. An overriding hint replaces the bound field's help_text, which
    is what Django reads; the form's field is left alone.
    """
    if hint is not None:
        bound_field.help_text = hint
    is_check = isinstance(bound_field.field.widget, forms.CheckboxInput)
    if optional is None:
        optional = not bound_field.field.required and not is_check
    return {
        "id": bound_field.auto_id,
        "label": bound_field.label if label is None else label,
        "hint": bound_field.help_text,
        "errors": list(bound_field.errors),
        "optional": optional,
        "is_check": is_check,
        "widget": bound_field.as_widget(),
    }
