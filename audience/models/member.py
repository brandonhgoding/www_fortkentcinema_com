from typing import ClassVar

from django.db import models


class MemberManager(models.Manager):
    pass


class Member(models.Model):
    """A cardholder.

    Family tiers cover the cardholder plus immediate family, but only the
    cardholder is stored — coverage stays honour-system at the box office,
    exactly as it works today.
    """

    objects: ClassVar[MemberManager] = MemberManager()

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)

    # Free text on purpose: people give us "543-7000" and "+1 207 555 0100"
    # alike, and validating a local roster's phone numbers buys nothing.
    phone = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "Member"
        verbose_name_plural = "Members"

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def save(self, *args, **kwargs) -> None:
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)
