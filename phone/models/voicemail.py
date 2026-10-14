from typing import ClassVar

from django.db import models
from django.db.models import Manager

from .call_log import CallLog


class VoicemailStatus(models.TextChoices):
    NEW = "NEW", "New"
    HANDLED = "HANDLED", "Handled"


class Voicemail(models.Model):
    """A message left on the phone line.

    Nothing in this project sends mail (see RentalInquiry), so this row
    IS the notification: the dashboard lists it and the smart-alert strip
    counts the NEW ones.

    Twilio reports a message in two webhooks — the recording when the caller
    hangs up, the transcript up to a minute later — and either can arrive
    first, so both upsert on `recording_sid`.
    """

    objects: ClassVar[Manager["Voicemail"]]

    call = models.ForeignKey(
        CallLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="voicemails",
    )
    recording_sid = models.CharField(max_length=64, unique=True)
    caller = models.CharField(max_length=32, blank=True)
    recording_url = models.URLField(blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    transcript = models.TextField(blank=True)
    # Twilio's TranscriptionStatus: "completed" or "failed". Blank until the
    # transcription webhook arrives.
    transcription_status = models.CharField(max_length=20, blank=True)

    status = models.CharField(
        max_length=20, choices=VoicemailStatus.choices, default=VoicemailStatus.NEW
    )
    # Staff-only, e.g. "Called back Tue, wants a rental quote".
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.caller or 'Unknown caller'} ({self.get_status_display()})"

    @property
    def audio_url(self) -> str:
        """Twilio serves the recording as WAV at the bare URL; MP3 is smaller
        and plays in every browser."""
        return f"{self.recording_url}.mp3" if self.recording_url else ""
