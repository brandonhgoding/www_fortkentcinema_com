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
    that is not required), the control, its error and its hint. The error
    and hint are tied to the control with aria-describedby, and an error
    sets aria-invalid. A checkbox renders as a .checkboxLabel row instead.

    `label` and `hint` override the form's own label and help_text.
    """
    is_check = isinstance(bound_field.field.widget, forms.CheckboxInput)
    control_id = bound_field.auto_id
    hint = bound_field.help_text if hint is None else hint
    errors = list(bound_field.errors)
    described = []
    if errors:
        described.append(f"{control_id}-error")
    if hint:
        described.append(f"{control_id}-hint")
    attrs = {}
    if described:
        attrs["aria-describedby"] = " ".join(described)
    if errors:
        attrs["aria-invalid"] = "true"
    if optional is None:
        optional = not bound_field.field.required and not is_check
    return {
        "id": control_id,
        "label": bound_field.label if label is None else label,
        "hint": hint,
        "errors": errors,
        "optional": optional,
        "is_check": is_check,
        "widget": bound_field.as_widget(attrs=attrs),
    }
