from django.db import models
from django.utils import timezone


class SalesPull(models.Model):
    """Run log: one row per pull command invocation per business date."""

    class Status(models.TextChoices):
        OK = "OK"
        FAILED = "FAILED"

    business_date = models.DateField()
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices)
    orders = models.PositiveIntegerField(default=0)
    lines = models.PositiveIntegerField(default=0)
    owner_email_sent = models.BooleanField(default=False)
    report_email_sent = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    # Website orders paid on the day that the pull did not store: the guard
    # for Square no longer returning them. Zero on a complete pull.
    missing_online = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-business_date", "-started_at"]

    def __str__(self) -> str:
        return f"{self.business_date} {self.status}"
