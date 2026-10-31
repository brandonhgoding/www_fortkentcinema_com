from collections.abc import Collection

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from .managers import UserManager, normalise


class User(AbstractUser):
    """The site's user, kept on the table Django's own User already used.

    Email is the login: there is no username, and the address is stored
    stripped and lowercased, unique ignoring case at the database.
    Existing staff accounts, their group memberships and the foreign keys
    pointing at them carry over on the same auth_user table.

    No personal names are stored: the email stands in wherever Django
    would show one.
    """

    username = None
    first_name = None
    last_name = None
    email = models.EmailField("email address")
    email_verified_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "auth_user"
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="accounts_user_email_ci_unique",
                violation_error_message="A user with that email already exists.",
            ),
        ]

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        # Normalise before validation, as Member does, so forms check the
        # stored form of the address.
        self.email = normalise(self.email)
        super().clean_fields(exclude=exclude)

    def clean(self) -> None:
        self.email = normalise(self.email)
        # AbstractUser.clean() hands the address to normalize_email, which
        # raises ValueError on a blank; the required field reports that.
        if self.email:
            super().clean()

    def save(self, *args, **kwargs) -> None:
        self.email = normalise(self.email)
        super().save(*args, **kwargs)

    def get_full_name(self) -> str:
        return self.email

    def get_short_name(self) -> str:
        return self.email
