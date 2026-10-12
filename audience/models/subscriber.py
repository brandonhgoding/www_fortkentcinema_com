import uuid
from datetime import timedelta
from collections.abc import Collection
from typing import ClassVar

from django.db import models, transaction
from django.utils import timezone


class SubscriberStatus(models.TextChoices):
    PENDING = "PENDING", "Pending confirmation"
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
        email = self._normalise(email)

        # get_or_create, not a lookup then create(): two simultaneous signups
        # for a new address both miss the lookup, and the second INSERT hits
        # the unique index. get_or_create inserts inside a savepoint and
        # re-fetches the winner's row on IntegrityError.
        return self.get_or_create(
            email=email,
            defaults={
                "source": source,
                "consent_ip": ip,
                "confirmed_at": timezone.now(),
            },
        )

    def request_signup(
        self, email: str, source: str, ip: str | None = None
    ) -> "Subscriber | None":
        """Start a double opt-in; return the row to email, or None.

        A new address is stored PENDING and joins the list only when it
        confirms. None means no email is due: the address is already on the
        list, or was sent one within CONFIRMATION_RESEND_AFTER, which stops
        the form being used to flood someone's inbox. An opted-out address
        is returned still opted out; only confirming brings it back.
        """
        email = self._normalise(email)
        sub, created = self.get_or_create(
            email=email,
            defaults={
                "source": source,
                "consent_ip": ip,
                "status": SubscriberStatus.PENDING,
            },
        )
        if created:
            return sub
        if sub.status == SubscriberStatus.ACTIVE:
            return None
        sent = sub.confirmation_sent_at
        if (
            sent is not None
            and timezone.now() - sent < Subscriber.CONFIRMATION_RESEND_AFTER
        ):
            return None
        return sub

    @staticmethod
    def _normalise(email: str) -> str:
        email = (email or "").strip().lower()
        if not email:
            raise ValueError("email is required")
        if len(email) > Subscriber.EMAIL_MAX_LENGTH:
            # Postgres would refuse the INSERT with a DataError.
            raise ValueError("email is too long")
        return email

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

    # How long before a pending or opted-out address may be emailed again.
    CONFIRMATION_RESEND_AFTER: ClassVar[timedelta] = timedelta(hours=1)

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

    # When the address proved it is theirs by following the emailed link.
    # consent_at is when the form was submitted; this is when they joined.
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmation_sent_at = models.DateTimeField(null=True, blank=True)

    # Generated from the first row even though nothing sends mail yet.
    # Retrofitting tokens onto an existing list is a migration worth avoiding.
    unsubscribe_token = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    # Set only while confirm() saves, so _log_change can tell it apart from
    # a staff edit that also leaves the row ACTIVE.
    _confirming = False

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
        # The earlier opt-out is not lost: SubscriptionChange keeps it.
        if self.status == SubscriberStatus.UNSUBSCRIBED:
            if self.unsubscribed_at is None:
                self.unsubscribed_at = timezone.now()
        else:
            self.unsubscribed_at = None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "status" in update_fields:
            kwargs["update_fields"] = {*update_fields, "unsubscribed_at"}
        # An ACTIVE row is on the list, so it has a consent record: a row
        # made in the admin would otherwise have none. confirm() and record()
        # set their own, which this leaves alone.
        if self.status == SubscriberStatus.ACTIVE and self.confirmed_at is None:
            self.confirmed_at = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "confirmed_at"}

        adding = self._state.adding
        previous = (
            None
            if adding
            else Subscriber.objects.filter(pk=self.pk)
            .values_list("status", flat=True)
            .first()
        )
        with transaction.atomic():
            super().save(*args, **kwargs)
            if adding or previous != self.status:
                self._log_change()

    def _log_change(self) -> None:
        from .subscription_change import SubscriptionChange

        if self.status == SubscriberStatus.UNSUBSCRIBED:
            at = self.unsubscribed_at
        elif self.changes.exists():
            # confirm() stamps confirmed_at in the same instant, so the
            # history agrees with it. Any other re-subscribe (staff, via the
            # admin) leaves confirmed_at as the earlier join and is dated now.
            at = self.confirmed_at if self._confirming else timezone.now()
        else:
            at = self.consent_at
        SubscriptionChange.objects.create(subscriber=self, status=self.status, at=at)

    def unsubscribe(self) -> None:
        if self.status == SubscriberStatus.UNSUBSCRIBED:
            return
        self.status = SubscriberStatus.UNSUBSCRIBED
        self.unsubscribed_at = timezone.now()
        self.save(update_fields=["status", "unsubscribed_at"])

    def confirm(self) -> None:
        if self.status == SubscriberStatus.ACTIVE:
            return
        self.status = SubscriberStatus.ACTIVE
        self.confirmed_at = timezone.now()
        self._confirming = True
        try:
            self.save(update_fields=["status", "confirmed_at"])
        finally:
            self._confirming = False
