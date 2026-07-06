from cinema.models import Screen
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
