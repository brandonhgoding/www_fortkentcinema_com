
from cinema.models import Engagement
from django import forms

KIND_OPTIONS = [("REGULAR", "Regular"),
                ("CLASSIC", "Classic"), ("DOUBLE_FEATURE", "Double Feature")]
STATUS_OPTIONS = [("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"), ("CANCELLED", "Cancelled")]


class EngagementForm(forms.ModelForm):
    kind = forms.ChoiceField(choices=KIND_OPTIONS, widget=forms.Select(attrs={"class": "input"}))
    status = forms.ChoiceField(choices=STATUS_OPTIONS, widget=forms.Select(attrs={"class": "input"}))

    class Meta:
        model = Engagement
        fields = ["kind", "display_title", "screen", "start_date", "end_date",
                  "presentation_format", "language", "translation", "status", "show_in_main_listings",
                  "is_free_for_members", "in_ticket_report", "notes"]
        widgets = {
            "display_title": forms.TextInput(attrs={
                "class": "input", "placeholder": "e.g. Creature Double Feature"}),
            "screen": forms.Select(attrs={"class": "input"}),
            "start_date": forms.DateInput(attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"),
            "presentation_format": forms.Select(attrs={"class": "input"}),
            "language": forms.Select(attrs={"class": "input"}),
            "translation": forms.Select(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3,
                                           "placeholder": "Optional notes about this engagement..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["screen"].empty_label = "Select a screen"
        for name in ("start_date", "end_date"):
            self.fields[name].input_formats = ["%Y-%m-%d"]
