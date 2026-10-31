from django.contrib.auth.base_user import BaseUserManager


def normalise(email) -> str:
    """The stored form of an address: stripped and lowercased, "" for none.
    The one rule for everything that stores, counts or looks up an email,
    so "Staff@x.com" and " staff@x.com" are one person everywhere."""
    return str(email or "").strip().lower()


class UserManager(BaseUserManager):
    """Users are found and made by email; the address is the login."""

    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        # The whole address, not just the domain as the base class does:
        # "Staff@" and "staff@" are one person at a small cinema.
        email = normalise(email)
        if not email:
            raise ValueError("email is required")
        return email

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def _create_user(self, email, password, **extra_fields):
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
