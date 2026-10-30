"""Per-recipient pieces of the Thursday email."""

from django.urls import reverse

from audience.models import Subscriber
from boxoffice.site import base_url


def unsubscribe_url(subscriber: Subscriber) -> str:
    """The absolute one-click unsubscribe link for this recipient."""
    return base_url() + reverse("list_unsubscribe", args=[subscriber.unsubscribe_token])


def mask_email(email: str) -> str:
    """"brandon@example.com" -> "b•••@example.com", for the unsubscribe page."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}"
