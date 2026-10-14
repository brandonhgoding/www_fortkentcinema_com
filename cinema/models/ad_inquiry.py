from django.db import models

from .rental_inquiry import InquiryStatus


class AdType(models.TextChoices):
    SLIDE = "SLIDE", "Pre-show slide"
    VIDEO = "VIDEO", "Video spot"
    UNSURE = "UNSURE", "Not sure yet"


class AdInquiry(models.Model):
    """A local business asking to advertise before the show.

    Nothing in this project sends mail, so this row IS the
    notification. The dashboard lists it and the smart-alert strip
    counts the NEW ones.
    """

    business_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    ad_type = models.CharField(
        max_length=10, choices=AdType.choices, default=AdType.UNSURE
    )
    message = models.TextField(blank=True)

    status = models.CharField(
        max_length=20, choices=InquiryStatus.choices, default=InquiryStatus.NEW
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Ad inquiries"

    def __str__(self) -> str:
        return f"{self.business_name} ({self.get_status_display()})"
