from cinema.models import RentalInquiry
from django import forms


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
