from django import forms
from django.core.validators import validate_email


class ContactForm(forms.Form):
    name = forms.CharField(max_length=120)
    email = forms.EmailField(validators=[validate_email])
    # Optional phone: template already guards with `{% if form.phone %}`
    phone = forms.CharField(max_length=30, required=False)
    subject = forms.CharField(max_length=150)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}))

    # Honeypot to catch bots
    hp = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean_hp(self):
        if self.cleaned_data.get("hp"):
            raise forms.ValidationError("Spam detected.")
        return ""
