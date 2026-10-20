import re

from boxoffice.spec import SQUARE_TIERS
from django import forms

# Spaces and the punctuation people type in phone numbers; stripped before
# the length and digits check.
PHONE_PUNCTUATION = re.compile(r"[\s().\-/]")


def _quantity_field() -> forms.IntegerField:
    return forms.IntegerField(
        min_value=0,
        max_value=20,
        initial=0,
    )


class BuyForm(forms.Form):
    """The /tickets/<pk>/ form: how many of each ticket, and who is buying."""

    adult = _quantity_field()
    senior = _quantity_field()
    child = _quantity_field()
    name = forms.CharField(
        max_length=200,
        label="Your name",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    email = forms.EmailField(
        label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"})
    )
    phone = forms.CharField(
        max_length=40,
        label="Phone",
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
    )
    # Honeypot. A real person leaves this empty; bots fill every field.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    @property
    def is_bot(self) -> bool:
        return bool(self.data.get("website"))

    def clean_phone(self) -> str:
        phone = self.cleaned_data["phone"].strip()
        digits = PHONE_PUNCTUATION.sub("", phone)
        if not (7 <= len(digits) <= 20 and re.fullmatch(r"\+?\d+", digits)):
            raise forms.ValidationError(
                "Enter a phone number we can reach you at, like 207-555-0100."
            )
        return phone

    def clean(self):
        cleaned = super().clean()
        if all(cleaned.get(tier) == 0 for tier in SQUARE_TIERS):
            raise forms.ValidationError("Pick at least one ticket.")
        return cleaned

    def quantities(self) -> dict[str, int]:
        return {tier: self.cleaned_data[tier] for tier in SQUARE_TIERS}
