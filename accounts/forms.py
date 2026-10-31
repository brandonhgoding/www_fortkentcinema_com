from django import forms
from django.conf import settings
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    UsernameField,
)
from django.contrib.auth import get_user_model, password_validation
from django.core.cache import cache
from django.core.exceptions import ValidationError

from accounts.client_ip import bucket
from accounts.managers import normalise
from accounts.verification import ip_allowed


UNVERIFIED_MESSAGE = "Please confirm your email first. We can send a new link."


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

    unverified = False

    def confirm_login_allowed(self, user) -> None:
        """Runs only once the password was right, so saying the address is
        unconfirmed gives nothing away. Staff are exempt from confirming."""
        super().confirm_login_allowed(user)
        if not user.is_staff and user.email_verified_at is None:
            self.unverified = True
            raise ValidationError(UNVERIFIED_MESSAGE, code="unverified")


class EmailPasswordResetForm(PasswordResetForm):
    """Asks for the email to send a reset link to. An address is sent at most
    one link per PASSWORD_RESET_TIMEOUT, so nobody can flood a staff inbox and
    each address has only one live link at a time, and one connection gets
    the same hourly cap as registering. Known or not, the page answers the
    same way."""

    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def save(self, *args, request=None, **kwargs) -> None:
        # The honeypot "website" field, as on the site's other forms: hidden
        # from people, so filling it in marks a bot, which gets the same
        # reply and no email.
        if self.data.get("website"):
            return
        if not ip_allowed(bucket(request)):
            return
        email = normalise(self.cleaned_data["email"])
        # Only an address with an account claims a cache row: the cache is a
        # bounded table that culls its lowest keys first, and the sign-in
        # counters sort below these.
        if not any(True for _ in self.get_users(email)):
            return
        key = "password-reset:" + email
        if cache.add(key, True, settings.PASSWORD_RESET_TIMEOUT):
            super().save(*args, request=request, **kwargs)


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
        # An unsaved user lets the similarity validator compare the email.
        candidate = get_user_model()(email=self.cleaned_data.get("email", ""))
        password_validation.validate_password(password2, user=candidate)
        return password2


class DashboardPasswordChangeForm(PasswordChangeForm):
    """Django's change form with the dashboard's .input class on each box
    (components.css styles controls by class, not element), matching every
    other form the {% field %} tag renders."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"
