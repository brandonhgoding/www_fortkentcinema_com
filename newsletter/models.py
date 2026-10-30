"""The Thursday email's record: one Issue per week, one Delivery per
recipient. The Delivery's uniqueness is what makes a re-run safe."""

from django.db import models
from django.utils import timezone

UNSUBSCRIBE_PLACEHOLDER = "{unsubscribe_url}"


class Issue(models.Model):
    class Status(models.TextChoices):
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    week_of = models.DateField(unique=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.SENDING
    )
    subject = models.CharField(max_length=200, blank=True)
    # The rendered bodies, so the dashboard shows exactly what went out. The
    # unsubscribe link differs per recipient, so both carry the literal
    # placeholder and the sender substitutes it.
    html = models.TextField(blank=True)
    text = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skip_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-week_of"]

    def __str__(self) -> str:
        return f"Thursday email {self.week_of:%Y-%m-%d}"

    @property
    def is_done(self) -> bool:
        return self.status in (self.Status.SENT, self.Status.SKIPPED)

    @property
    def preview_html(self) -> str:
        return self.html.replace(UNSUBSCRIBE_PLACEHOLDER, "#")


class Delivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name="deliveries"
    )
    subscriber = models.ForeignKey(
        "audience.Subscriber", on_delete=models.CASCADE, related_name="deliveries"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "subscriber"],
                name="newsletter_delivery_once_per_issue",
            )
        ]

    def __str__(self) -> str:
        return f"{self.issue} to {self.subscriber_id}: {self.status}"
