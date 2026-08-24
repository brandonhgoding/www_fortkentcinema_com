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
        labels = {
            "business_name": "Business or organization",
            "contact_name": "Your name",
        }
        # `tier`, `studio_title` and `message` are rebuilt in __init__ below
        # (message to add a max_length with no model migration), so their
        # labels/widgets are set there rather than here — setting them twice
        # would invite the two copies to drift apart.

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
        # `message` is an unbounded TextField on the model, written by an
        # anonymous POST. Cap it here at the form level (no model migration)
        # so a single request can't stash megabytes in one row.
        self.fields["message"] = forms.CharField(
            required=False,
            max_length=2000,
            widget=forms.Textarea(attrs={"rows": 4}),
            error_messages={
                "max_length": "Please keep this under 2,000 characters.",
            },
        )

    @property
    def is_bot(self) -> bool:
        return bool(self.data.get("website"))
