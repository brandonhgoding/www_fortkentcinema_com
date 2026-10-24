from django import forms
from django.conf import settings
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    UsernameField,
)
from django.contrib.auth import password_validation
from django.core.cache import cache
from django.core.exceptions import ValidationError

from accounts.verification import normalise


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


class EmailPasswordResetForm(PasswordResetForm):
    """Asks for the email to send a reset link to. An address is sent at most
    one link per PASSWORD_RESET_TIMEOUT, so nobody can flood a staff inbox and
    each address has only one live link at a time. Known or not, the page
    answers the same way."""

    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def save(self, *args, **kwargs) -> None:
        # The honeypot "website" field, as on the site's other forms: hidden
        # from people, so filling it in marks a bot, which gets the same
        # reply and no email.
        if self.data.get("website"):
            return
        # The in-process cache, so each server worker counts on its own: a
        # soft limit, which is all flooding protection needs.
        key = "password-reset:" + self.cleaned_data["email"].strip().lower()
        if cache.add(key, True, settings.PASSWORD_RESET_TIMEOUT):
            super().save(*args, **kwargs)


class ResendForm(forms.Form):
    """Asks for the address to send a fresh confirmation link to. "website"
    is the honeypot, as on the site's other forms."""

    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    website = forms.CharField(required=False)

    def clean_email(self) -> str:
        return normalise(self.cleaned_data["email"])


class RegisterForm(ResendForm):
    """Email, a password twice (checked as Django's SetPasswordForm does),
    and the honeypot."""

    error_messages = {"password_mismatch": "The two password fields didn’t match."}

    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Password again",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_password2(self) -> str:
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError(
                self.error_messages["password_mismatch"], code="password_mismatch"
            )
        password_validation.validate_password(password2, user=None)
        return password2
