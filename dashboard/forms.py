from cinema.models import Engagement, Poll, Screen
from django import forms

# Labels match the leprinceos SPA (note: "standard" sound shows "Standard",
# not the model's "Standard Surround").
SOUND_SYSTEM_CHOICES = [
    ("standard", "Standard"),
    ("dolby_digital", "Dolby Digital"),
    ("dolby_atmos", "Dolby Atmos"),
]


class ScreenForm(forms.ModelForm):
    sound_system = forms.ChoiceField(
        choices=SOUND_SYSTEM_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
    )

    class Meta:
        model = Screen
        fields = [
            "name", "capacity", "screen_type", "aspect_ratio",
            "sound_system", "supports_3d",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g., Screen 1, Main Auditorium"}
            ),
            "capacity": forms.NumberInput(
                attrs={"class": "input", "min": "1", "placeholder": "e.g., 150"}
            ),
            "screen_type": forms.Select(attrs={"class": "input"}),
            "aspect_ratio": forms.Select(attrs={"class": "input"}),
        }


KIND_OPTIONS = [("REGULAR", "Regular"), ("SPECIAL_EVENT", "Special Event"),
                ("CLASSIC", "Classic"), ("DOUBLE_FEATURE", "Double Feature")]
STATUS_OPTIONS = [("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"), ("CANCELLED", "Cancelled")]


class EngagementForm(forms.ModelForm):
    kind = forms.ChoiceField(choices=KIND_OPTIONS, widget=forms.Select(attrs={"class": "input"}))
    status = forms.ChoiceField(choices=STATUS_OPTIONS, widget=forms.Select(attrs={"class": "input"}))

    class Meta:
        model = Engagement
        fields = ["kind", "event_title", "screen", "start_date", "end_date",
                  "presentation_format", "status", "show_in_main_listings", "notes"]
        widgets = {
            "event_title": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. Creature Double Feature"}),
            "screen": forms.Select(attrs={"class": "input"}),
            "start_date": forms.DateInput(attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"),
            "presentation_format": forms.Select(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3,
                                           "placeholder": "Optional notes about this engagement..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["screen"].empty_label = "Select a screen"
        for name in ("start_date", "end_date"):
            self.fields[name].input_formats = ["%Y-%m-%d"]


class PollForm(forms.ModelForm):
    class Meta:
        model = Poll
        fields = ["title", "blurb", "opens_at", "closes_at", "results_visible"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input"}),
            "blurb": forms.Textarea(attrs={"class": "input", "rows": 3}),
            "opens_at": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"}
            ),
            "closes_at": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"}
            ),
        }
        labels = {
            "blurb": "Blurb (shown above the ballot)",
            "results_visible": "Show running tallies while voting is open",
        }
