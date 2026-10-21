"""Report a half-configured Twilio at startup, not on the first call."""

from django.conf import settings
from django.core import checks


@checks.register("phone")
def check_twilio_settings(app_configs, **kwargs) -> list[checks.CheckMessage]:
    """A blank token is the deliberate off switch and says nothing. With a
    token set, two silent half-states are worth a Warning: signatures
    checked against a URL Django cannot rebuild behind nginx (every call
    403s), and no account SID (the dashboard can't play or delete)."""
    if not settings.TWILIO_AUTH_TOKEN:
        return []
    messages: list[checks.CheckMessage] = []
    if (
        not settings.DEBUG
        and not settings.TWILIO_WEBHOOK_BASE_URL
        and not settings.SECURE_PROXY_SSL_HEADER
    ):
        messages.append(
            checks.Warning(
                "TWILIO_WEBHOOK_BASE_URL is blank and no proxy headers are "
                "trusted, so Twilio signatures are checked against the URL "
                "Django rebuilds itself: behind nginx every call gets a 403.",
                hint="Set TWILIO_WEBHOOK_BASE_URL to the public base URL "
                "(https://www.fortkentcinema.com) or USE_PROXY_HEADERS=True.",
                id="phone.W001",
            )
        )
    if not settings.TWILIO_ACCOUNT_SID:
        messages.append(
            checks.Warning(
                "TWILIO_ACCOUNT_SID is blank: the dashboard can't play or "
                "delete voicemail recordings.",
                hint="Set TWILIO_ACCOUNT_SID (AC...) from the Twilio console.",
                id="phone.W002",
            )
        )
    return messages
