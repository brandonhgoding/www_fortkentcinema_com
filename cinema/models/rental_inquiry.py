from django.db import models

from .sponsorship_inquiry import InquiryStatus


class RentalInquiry(models.Model):
    """Someone asking to book the theater for a private event.

    Same arrangement as SponsorshipInquiry: nothing in this project sends
    mail, so this row IS the notification. The dashboard lists it and the
    smart-alert strip counts the NEW ones. It replaced the owner's personal
    email address on /rentals/, which was the only written way to ask.
    """

    contact_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)

    # All optional: plenty of people ask "are you free some Saturday?"
    # before they have a date, a headcount or a film. Asking for those up
    # front would turn a quick question into a form they abandon.
    preferred_date = models.DateField(null=True, blank=True)
    guests = models.PositiveIntegerField(null=True, blank=True)
    # Free text rather than choices — birthday, gaming, their own DVD, a
    # licensed film — because the answer is usually a mix of those.
    event_type = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)

    status = models.CharField(
        max_length=20, choices=InquiryStatus.choices, default=InquiryStatus.NEW
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Rental inquiries"

    def __str__(self) -> str:
        return f"{self.contact_name} ({self.get_status_display()})"
