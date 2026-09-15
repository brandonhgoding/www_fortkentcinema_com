from django.conf import settings
from django.db import models
from django.utils import timezone


class FreeAdmission(models.Model):
    """One free admission, given to one member, on one day.

    Deliberately not linked to a showtime: the counter records that the
    benefit was used, not what was watched. Asking whoever is serving to
    pick a screening from a list would buy that answer with friction on
    every transaction, and a nullable link can be added later without
    disturbing a single existing row.

    There is no constraint stopping a member exceeding their tier's monthly
    allowance. The allowance is a policy the UI warns about and staff may
    override — encoding it as an invariant would make the supported
    workflow impossible.
    """

    member = models.ForeignKey(
        "audience.Member",
        related_name="free_admissions",
        on_delete=models.CASCADE,
    )
    redeemed_on = models.DateField(
        default=timezone.localdate,
        help_text="Which calendar month this counts against.",
    )
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Cleared rather than deleted if the staff account goes away.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-redeemed_on", "-created_at"]
        verbose_name = "Free admission"
        verbose_name_plural = "Free admissions"

    def __str__(self) -> str:
        return f"{self.member.full_name} — {self.redeemed_on}"
