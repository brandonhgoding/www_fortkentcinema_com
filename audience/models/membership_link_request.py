from django.conf import settings
from django.db import models
from django.utils import timezone


class LinkRequestStatus(models.TextChoices):
    NEW = "NEW", "New"
    DONE = "DONE", "Done"


class MembershipLinkRequest(models.Model):
    """A signed-in member asking staff to attach the roster row that carries
    another email address to their dashboard account.

    The member home shows the membership whose Member.email equals the
    account email; when nothing matches, the member can send this with the
    name on their membership. Like the rental and ad inquiries, the row is
    the notification: the dashboard lists it and the home alert strip counts
    the open ones. Staff resolve it by editing the roster row's email to
    the account email, and the next visit to the member home closes it.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membership_link_requests",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=10, choices=LinkRequestStatus.choices, default=LinkRequestStatus.NEW
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} ({self.get_status_display()})"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def mark_done(self) -> None:
        self.status = LinkRequestStatus.DONE
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "resolved_at"])

    def reopen(self) -> None:
        self.status = LinkRequestStatus.NEW
        self.resolved_at = None
        self.save(update_fields=["status", "resolved_at"])
