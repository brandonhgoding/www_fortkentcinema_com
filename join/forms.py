from django import forms


class JoinForm(forms.Form):
    """The /membership/join/<slug>/ form: who the membership is for."""

    # Two boxes, not one: the roster and Square customers carry given and
    # family names, and the roster sorts by the family name.
    first_name = forms.CharField(
        max_length=100,
        label="First name",
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=100,
        label="Last name",
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"})
    )
    # Honeypot. A real person leaves this empty; bots fill every field.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    @property
    def is_bot(self) -> bool:
        return bool(self.data.get("website"))
