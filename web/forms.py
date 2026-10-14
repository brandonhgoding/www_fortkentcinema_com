from cinema.models import AdInquiry, AdType, RentalInquiry
from django import forms

from web.constants import AD_SLIDE_PRICE, AD_VIDEO_PRICE


class RentalInquiryForm(forms.ModelForm):
    """The /rentals/ "Ready to book?" form.

    Only name and email are required: the rest is what the owner would ask on the phone
    anyway, and a lead with blanks is still a lead.
    """

    # Honeypot. A real person leaves this empty; bots fill every field.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = RentalInquiry
        fields = [
            "contact_name", "email", "phone",
            "preferred_date", "guests", "event_type", "message",
        ]
        labels = {
            "contact_name": "Your name",
            "phone": "Phone (optional)",
            "preferred_date": "Date you have in mind (optional)",
            "event_type": "What's the occasion? (optional)",
        }
        widgets = {
            # A native date picker; Django's DateInput defaults to type="text".
            # The picker only understands ISO dates, hence the format.
            "preferred_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "event_type": forms.TextInput(
                attrs={"placeholder": "Birthday, gaming, your own DVD, a film"}
            ),
        }
        # `guests` and `message` are rebuilt in __init__ below, so their
        # labels/widgets live there.

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The model's PositiveIntegerField allows 0; a party of nobody is a
        # typo, not a booking. min_value also renders min="1" on the input.
        self.fields["guests"] = forms.IntegerField(
            required=False,
            min_value=1,
            label="How many guests (optional)",
        )
        # Capped at the form level: an unbounded TextField written by an
        # anonymous POST.
        self.fields["message"] = forms.CharField(
            required=False,
            max_length=2000,
            label="Anything else (optional)",
            widget=forms.Textarea(attrs={"rows": 4}),
            error_messages={
                "max_length": "Please keep this under 2,000 characters.",
            },
        )

    @property
    def is_bot(self) -> bool:
        return bool(self.data.get("website"))


class AdInquiryForm(forms.ModelForm):
    """The /advertise/ "Get started" form.

    Business name, contact name and email are required; the rest is what the
    owner would ask on the phone anyway.
    """

    # Honeypot. A real person leaves this empty; bots fill every field.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = AdInquiry
        fields = [
            "business_name", "contact_name", "email", "phone",
            "ad_type", "message",
        ]
        labels = {
            "business_name": "Business name",
            "contact_name": "Your name",
            "phone": "Phone (optional)",
        }
        # `ad_type` and `message` are rebuilt in __init__ below, so their
        # labels/widgets live there.

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Rebuilt rather than taken from the model: the model's choices would
        # make it required and would not carry the prices. An empty
        # submission means "not sure yet" (see clean_ad_type).
        self.fields["ad_type"] = forms.ChoiceField(
            required=False,
            widget=forms.RadioSelect,
            initial=AdType.UNSURE,
            label="What are you interested in?",
            choices=[
                (AdType.SLIDE, f"Pre-show slide, ${AD_SLIDE_PRICE} a month"),
                (AdType.VIDEO, f"Video spot, ${AD_VIDEO_PRICE} a month"),
                (AdType.UNSURE, "Not sure yet"),
            ],
        )
        # Capped at the form level: an unbounded TextField written by an
        # anonymous POST.
        self.fields["message"] = forms.CharField(
            required=False,
            max_length=2000,
            label="Anything else? (optional)",
            widget=forms.Textarea(attrs={"rows": 4}),
            error_messages={
                "max_length": "Please keep this under 2,000 characters.",
            },
        )

    def clean_ad_type(self) -> str:
        return self.cleaned_data.get("ad_type") or AdType.UNSURE

    @property
    def is_bot(self) -> bool:
        return bool(self.data.get("website"))
