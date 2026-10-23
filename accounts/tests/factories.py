"""Test factory: every test makes its users here, by email."""

from django.contrib.auth import get_user_model


def make_user(email: str = "user@example.com", password: str = "pw12345", **extra):
    """Create a user who logs in with this email."""
    return get_user_model().objects.create_user(email, password, **extra)
