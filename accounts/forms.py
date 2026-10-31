from django import forms
from django.conf import settings
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    UsernameField,
)
from django.core.cache import cache
from django.core.exceptions import ValidationError

from accounts.client_ip import bucket
from accounts.managers import normalise
from accounts import throttle

# One connection may ask for this many reset emails an hour.
RESET_IP_CAP = 5
RESET_IP_WINDOW = 3600


def ip_allowed(ip: str) -> bool:
    """Count this request against the address's hourly cap (ip is the
    client_ip.bucket() of the request)."""
    return throttle.bump(f"password-reset:ip:{ip}", RESET_IP_WINDOW) <= RESET_IP_CAP


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

    def confirm_login_allowed(self, user) -> None:
        """Runs only once the password was right. Only staff sign in; any
        other account gets the same reply as a wrong password, so the page
        says nothing about which addresses have accounts."""
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError(
                self.error_messages["invalid_login"], code="invalid_login"
            )


class EmailPasswordResetForm(PasswordResetForm):
    """Asks for the email to send a reset link to. An address is sent at most
    one link per PASSWORD_RESET_TIMEOUT, so nobody can flood a staff inbox and
    each address has only one live link at a time, and one connection gets
    an hourly cap. Only staff accounts get links. Known or not, the page
    answers the same way."""

    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def get_users(self, email):
        # Only staff sign in, so only staff get a link.
        return (user for user in super().get_users(email) if user.is_staff)

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


class DashboardPasswordChangeForm(PasswordChangeForm):
    """Django's change form with the dashboard's .input class on each box
    (components.css styles controls by class, not element), matching every
    other form the {% field %} tag renders."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"
