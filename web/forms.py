from cinema.models import SponsorshipInquiry, StudioTitle
from django import forms

from .constants import SPONSORSHIP_TIERS


class SponsorshipInquiryForm(forms.ModelForm):
    # Honeypot. A real person leaves this empty; bots fill every field they
    # find. Same trick as the vote page's email capture.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = SponsorshipInquiry
        fields = [
            "business_name", "contact_name", "email", "phone",
            "tier", "studio_title", "message",
        ]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "business_name": "Business or organization",
            "contact_name": "Your name",
        }
        # `tier` and `studio_title` are rebuilt in __init__ below, so their
        # labels are set there rather than here — setting them twice would
        # invite the two copies to drift apart.

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["tier"] = forms.ChoiceField(
            required=False,
            label="What you'd like to cover (optional)",
            choices=[("", "Not sure yet")]
            + [
                (t["key"], f"{t['name']} — from ${t['price']}")
                for t in SPONSORSHIP_TIERS
            ],
        )
        self.fields["studio_title"] = forms.ModelChoiceField(
            required=False,
            label="Film you have in mind (optional)",
            queryset=StudioTitle.objects.available(),
            empty_label="Not sure yet",
        )
        self.fields["phone"].required = False
        self.fields["message"].required = False

    @property
    def is_bot(self) -> bool:
        return bool(self.data.get("website"))
