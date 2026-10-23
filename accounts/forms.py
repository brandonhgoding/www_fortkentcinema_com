from django import forms
from django.contrib.auth.forms import AuthenticationForm, UsernameField


class EmailAuthenticationForm(AuthenticationForm):
    """The sign-in form, asking for an email. The field keeps the name
    "username" because LoginView and django-axes both read it by that name."""

    username = UsernameField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # UsernameField.widget_attrs forces autocomplete="username", which
        # beats the widget's own attrs; for an email field browsers want this.
        self.fields["username"].widget.attrs["autocomplete"] = "email"

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Invalid email or password.",
    }
