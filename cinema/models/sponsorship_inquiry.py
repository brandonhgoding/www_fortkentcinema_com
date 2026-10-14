from django.db import models

from .rental_inquiry import InquiryStatus


class SponsorshipInquiry(models.Model):
    """A business asking about sponsoring a screening.

    Nothing in this project sends mail, so this row IS the notification: the
    dashboard lists it and the smart-alert strip counts the NEW ones. A lead
    that sits unseen is a lost sponsor, which is why it is surfaced twice.
    """

    business_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    message = models.TextField(blank=True)

    # Both optional: a business may want to sponsor *something* without
    # having picked a film or a level yet.
    studio_title = models.ForeignKey(
        "cinema.StudioTitle",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inquiries",
    )
    tier = models.CharField(max_length=32, blank=True)

    status = models.CharField(
        max_length=20, choices=InquiryStatus.choices, default=InquiryStatus.NEW
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Sponsorship inquiries"

    def __str__(self) -> str:
        return f"{self.business_name} ({self.get_status_display()})"
