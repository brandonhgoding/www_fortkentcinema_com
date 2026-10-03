import uuid
from collections.abc import Collection
from typing import ClassVar

from django.db import models
from django.utils import timezone


class SubscriberStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    UNSUBSCRIBED = "UNSUBSCRIBED", "Unsubscribed"


class SubscriberManager(models.Manager):
    def record(
        self, email: str, source: str, ip: str | None = None
    ) -> tuple["Subscriber", bool]:
        """Idempotently record an opt-in.

        Returns (subscriber, created). An address that has previously
        unsubscribed is returned untouched — a later signup must never
        silently re-add someone who opted out.
        """
        email = (email or "").strip().lower()
        if not email:
            raise ValueError("email is required")
        if len(email) > self.model.EMAIL_MAX_LENGTH:
            # Postgres would refuse the INSERT with a DataError.
            raise ValueError("email is too long")

        # get_or_create, not a lookup then create(): two simultaneous signups
        # for a new address both miss the lookup, and the second INSERT hits
        # the unique index. get_or_create inserts inside a savepoint and
        # re-fetches the winner's row on IntegrityError.
        return self.get_or_create(
            email=email, defaults={"source": source, "consent_ip": ip}
        )

    def active(self) -> models.QuerySet["Subscriber"]:
        return self.filter(status=SubscriberStatus.ACTIVE)


class Subscriber(models.Model):
    """A person who asked to hear from us.

    Deliberately generic: nothing here references films or polls. `source` is
    only a label, so the next feature that needs an email list reuses this
    model rather than growing its own.
    """

    objects: ClassVar[SubscriberManager] = SubscriberManager()

    # EmailField's default, spelled out because validate_email accepts up
    # to 320 characters: anything taking addresses must check this too.
    EMAIL_MAX_LENGTH: ClassVar[int] = 254

    email = models.EmailField(unique=True, max_length=EMAIL_MAX_LENGTH)
    status = models.CharField(
        max_length=20,
        choices=SubscriberStatus.choices,
        default=SubscriberStatus.ACTIVE,
    )
    source = models.CharField(
        max_length=32,
        help_text="Where the opt-in happened, e.g. 'poll_vote'.",
    )

    # Consent record. Kept because CAN-SPAM compliance means being able to
    # show when and from where someone opted in.
    consent_at = models.DateTimeField(auto_now_add=True)
    consent_ip = models.GenericIPAddressField(null=True, blank=True)

    # Generated from the first row even though nothing sends mail yet.
    # Retrofitting tokens onto an existing list is a migration worth avoiding.
    unsubscribe_token = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-consent_at"]
        verbose_name = "Subscriber"
        verbose_name_plural = "Subscribers"

    def __str__(self) -> str:
        return self.email

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        # Normalise before validation so validate_unique, which a ModelForm
        # runs before save(), compares the lowercased address. Same as Member.
        self.email = (self.email or "").strip().lower()
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs) -> None:
        self.email = (self.email or "").strip().lower()
        # status and unsubscribed_at must agree however the row is saved —
        # the admin's Status dropdown bypasses unsubscribe(). An opt-out
        # keeps any time already recorded; a re-subscribe (staff acting on
        # fresh consent) clears it, so an active row never reads as opted out.
        if self.status == SubscriberStatus.UNSUBSCRIBED:
            if self.unsubscribed_at is None:
                self.unsubscribed_at = timezone.now()
        else:
            self.unsubscribed_at = None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "status" in update_fields:
            kwargs["update_fields"] = {*update_fields, "unsubscribed_at"}
        super().save(*args, **kwargs)

    def unsubscribe(self) -> None:
        if self.status == SubscriberStatus.UNSUBSCRIBED:
            return
        self.status = SubscriberStatus.UNSUBSCRIBED
        self.unsubscribed_at = timezone.now()
        self.save(update_fields=["status", "unsubscribed_at"])
