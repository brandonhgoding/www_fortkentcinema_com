from django import forms
from django.template import Context, Template
from django.test import SimpleTestCase


class _Form(forms.Form):
    name = forms.CharField(help_text="Shown on the card.")
    phone = forms.CharField(required=False)
    url = forms.URLField(required=False, help_text="For the admin.")
    listed = forms.BooleanField(required=False)


def render(form, tag):
    return Template("{% load dashboard_extras %}" + tag).render(Context({"form": form}))


class FieldTagTests(SimpleTestCase):
    """The {% field %} tag behind every drawer form field."""

    def test_label_control_and_hint_are_tied_together(self) -> None:
        html = render(_Form(), '{% field form.name label="Name" %}')
        self.assertIn('<label for="id_name">Name</label>', html)
        self.assertIn('aria-describedby="id_name_helptext"', html)
        self.assertIn(
            '<p class="fieldHint" id="id_name_helptext">Shown on the card.</p>', html
        )

    def test_error_sets_aria_invalid_and_is_described(self) -> None:
        form = _Form(data={"name": ""})
        form.is_valid()
        html = render(form, "{% field form.name %}")
        self.assertIn('aria-invalid="true"', html)
        self.assertIn('aria-describedby="id_name_helptext id_name_error"', html)
        self.assertIn('<p class="field-error" id="id_name_error">', html)

    def test_optional_marker_only_on_fields_that_are_not_required(self) -> None:
        self.assertIn("fieldOptional", render(_Form(), "{% field form.phone %}"))
        self.assertNotIn("fieldOptional", render(_Form(), "{% field form.name %}"))
        self.assertNotIn("fieldOptional", render(_Form(), "{% field form.listed %}"))

    def test_empty_hint_hides_help_text_and_its_reference(self) -> None:
        html = render(_Form(), '{% field form.url hint="" %}')
        self.assertNotIn("For the admin.", html)
        self.assertNotIn("aria-describedby", html)

    def test_checkbox_renders_as_a_checkbox_row(self) -> None:
        html = render(_Form(), '{% field form.listed label="Listed" %}')
        self.assertIn(
            '<label class="checkboxLabel" for="id_listed"><input type="checkbox"', html
        )
