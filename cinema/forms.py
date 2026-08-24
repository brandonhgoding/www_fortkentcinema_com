"""Forms for the cinema admin."""

from cinema.studio_import import DEFAULT_SHEET, studio_choices
from django import forms


class StudioCatalogImportForm(forms.Form):
    """Upload a studio's availability list from the StudioTitle changelist.

    The same work `manage.py import_studio_catalog` does, for the times a
    list arrives while nobody is near a terminal.
    """

    studio = forms.ChoiceField(
        label="Studio",
        help_text="A studio missing here can be added under Studios first.",
    )
    file = forms.FileField(
        label="Catalog file",
        help_text="The .xlsx the studio sent, or a .csv of the same columns.",
    )
    sheet = forms.CharField(
        label="Worksheet",
        required=False,
        initial=DEFAULT_SHEET,
        help_text=(
            "Which sheet to read from an .xlsx. Universal ships 'by DATE' and "
            "'by TITLE' with identical content, so the default is fine. "
            "Ignored for a .csv."
        ),
    )
    dry_run = forms.BooleanField(
        label="Preview only",
        required=False,
        initial=True,
        help_text="Report what the file would do and stop, writing nothing.",
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Built per request so a studio added a minute ago is selectable.
        self.fields["studio"].choices = studio_choices()

    def clean_sheet(self) -> str:
        return self.cleaned_data["sheet"].strip() or DEFAULT_SHEET
