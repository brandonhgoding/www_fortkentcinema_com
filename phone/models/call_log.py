from typing import ClassVar

from django.db import models
from django.db.models import Manager
from django.utils import timezone


class CallLog(models.Model):
    """One inbound call to the phone line.

    Created when Twilio first hits the incoming-call webhook and appended to
    as the caller presses keys, so admin shows what people actually ask the
    line for — which is the evidence for what the Level 2 agent should cover.
    """

    objects: ClassVar[Manager["CallLog"]]

    # Twilio's id for the call. Every webhook in a call carries it, which is
    # how the menu and voicemail webhooks find this row again.
    call_sid = models.CharField(max_length=64, unique=True)
    # E.164 from the phone network, but a SIP URI or client identifier
    # from anywhere else, and Postgres rejects a value the column can't
    # hold: wide enough for whatever Twilio sends.
    caller = models.CharField(max_length=255, blank=True)
    called = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    # Keys pressed at the menu, in order: "1", "2", "3", an invalid digit as
    # pressed, or "none" when the caller let the menu time out.
    choices = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        started = timezone.localtime(self.started_at)
        return f"{self.caller or 'Unknown caller'} @ {started:%Y-%m-%d %H:%M}"

    def add_choice(self, choice: str) -> None:
        self.choices = [*self.choices, choice]
        self.save(update_fields=["choices"])
