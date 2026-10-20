from django.db import models


class EmailReport(models.Model):
    """One nightly email the pull sends; the owner manages its recipients."""

    class Kind(models.TextChoices):
        OWNER_SUMMARY = "OWNER_SUMMARY", "Owner summary"
        TICKET_REPORT = "TICKET_REPORT", "Ticket report"

    kind = models.CharField(max_length=20, choices=Kind.choices, unique=True)
    subject = models.CharField(max_length=200)
    enabled = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.get_kind_display()

    def to_addresses(self) -> list[str]:
        return list(
            self.recipients.filter(cc=False)
            .order_by("address")
            .values_list("address", flat=True)
        )

    def cc_addresses(self) -> list[str]:
        return list(
            self.recipients.filter(cc=True)
            .order_by("address")
            .values_list("address", flat=True)
        )


class EmailRecipient(models.Model):
    report = models.ForeignKey(
        EmailReport, on_delete=models.CASCADE, related_name="recipients"
    )
    address = models.EmailField()
    cc = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["report", "address"],
                name="boxoffice_unique_recipient_per_report",
            ),
        ]

    def __str__(self) -> str:
        return self.address

    def clean(self) -> None:
        # Before the unique check, so the admin catches "Owner@" vs "owner@".
        self.address = self.address.strip().lower()

    def save(self, *args, **kwargs) -> None:
        self.address = self.address.strip().lower()
        super().save(*args, **kwargs)
