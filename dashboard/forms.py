from audience.dates import add_months
from audience.models import Member, MembershipTerm
from cinema.models import Engagement, Poll, Screen
from django import forms
from web.constants import MEMBERSHIP, MEMBERSHIP_BY_SLUG

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
                  "presentation_format", "status", "show_in_main_listings",
                  "is_free_for_members", "notes"]
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


# The tier catalogue lives in web.constants; `audience` cannot import it
# (web imports audience), so validation against it happens here.
MEMBERSHIP_TIER_CHOICES = [(t["slug"], t["name"]) for t in MEMBERSHIP]


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["first_name", "last_name", "email", "phone", "notes"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
            "phone": forms.TextInput(
                attrs={"class": "input", "placeholder": "optional"}
            ),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 3}),
        }

    def clean_email(self) -> str:
        # Member.save() lowercases; normalise here too so the uniqueness
        # check catches "ADA@" against a stored "ada@".
        return (self.cleaned_data["email"] or "").strip().lower()


class MembershipTermForm(forms.ModelForm):
    tier = forms.ChoiceField(
        choices=MEMBERSHIP_TIER_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
    )

    class Meta:
        model = MembershipTerm
        fields = [
            "tier", "started_on", "expires_on",
            "price_paid", "purchased_at", "notes",
        ]
        widgets = {
            "started_on": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "expires_on": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "purchased_at": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "price_paid": forms.NumberInput(
                attrs={"class": "input", "step": "0.01", "min": "0"}
            ),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 2}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Both are filled from the tier when left blank, so staff can add a
        # renewal by choosing a tier and a start date and nothing else.
        self.fields["expires_on"].required = False
        self.fields["price_paid"].required = False

    def clean(self):
        cleaned = super().clean()
        tier = MEMBERSHIP_BY_SLUG.get(cleaned.get("tier"))
        started_on = cleaned.get("started_on")
        if tier is None:
            return cleaned

        if started_on and not cleaned.get("expires_on"):
            cleaned["expires_on"] = add_months(started_on, tier["duration_months"])
        if cleaned.get("price_paid") is None:
            cleaned["price_paid"] = tier["price"]

        expires_on = cleaned.get("expires_on")
        if started_on and expires_on and expires_on < started_on:
            self.add_error("expires_on", "Expiry cannot be before the start date.")
        return cleaned
