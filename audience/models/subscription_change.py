from django.db import models
from django.utils import timezone

from .subscriber import SubscriberStatus


class SubscriptionChange(models.Model):
    """One opt-in or opt-out, kept for good.

    Subscriber holds only the current state: re-subscribing clears
    unsubscribed_at so an active row never reads as opted out. This log is
    the history behind it: every time someone joined the list or left it.
    Subscriber.save() writes it; nothing edits it.

    Deleted with the subscriber, so erasing a person's data erases this too.
    """

    subscriber = models.ForeignKey(
        "audience.Subscriber",
        related_name="changes",
        on_delete=models.CASCADE,
    )
    status = models.CharField(max_length=20, choices=SubscriberStatus.choices)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-at", "-id"]
        verbose_name = "Subscription change"
        verbose_name_plural = "Subscription changes"

    def __str__(self) -> str:
        return f"{self.subscriber.email}: {self.get_status_display()} at {self.at}"
