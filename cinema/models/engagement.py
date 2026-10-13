from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Manager
from django.utils import timezone

from .film import Film
from .screen import Screen


class EngagementStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"
    CANCELLED = "CANCELLED", "Cancelled"
    ENDED = "ENDED", "Ended"


class Language(models.TextChoices):
    ENGLISH = "english", "English"
    FRENCH = "french", "French"


class Engagement(models.Model):
    objects: ClassVar[Manager["Engagement"]]

    # What a film with no known runtime is assumed to run when booking a
    # screen. Long enough that a guess errs towards a gap, not an overlap.
    UNKNOWN_RUNTIME_MINUTES = 150

    films = models.ManyToManyField(
        Film, through="cinema.EngagementFilm", related_name="engagements"
    )
    # screen = intended/default screen for this run
    screen = models.ForeignKey(
        Screen, on_delete=models.PROTECT, related_name="engagements"
    )

    start_date = models.DateField()
    end_date = models.DateField()

    FORMAT_CHOICES = [
        ("2d", "2D"),
        ("3d", "3D"),
    ]
    presentation_format = models.CharField(
        max_length=2,
        choices=FORMAT_CHOICES,
        default="2d",
    )
    # The version of the film being played, which can differ from the
    # film's original language (a dubbed print, say).
    language = models.CharField(
        max_length=20, choices=Language.choices, default=Language.ENGLISH
    )

    class Kind(models.TextChoices):
        REGULAR = "REGULAR", "Regular"
        SPECIAL_EVENT = "SPECIAL_EVENT", "Special Event"
        CLASSIC = "CLASSIC", "Classic"
        DOUBLE_FEATURE = "DOUBLE_FEATURE", "Double Feature"

    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.REGULAR
    )
    event_title = models.CharField(max_length=200, blank=True)
    show_in_main_listings = models.BooleanField(default=True)
    is_free_for_members = models.BooleanField(
        default=False,
        help_text="Show a 'Free for Members' badge on the public listings "
        "and movie page for this run.",
    )
    in_ticket_report = models.BooleanField(
        default=True,
        help_text="Include this run's ticket sales in the nightly ticket report "
        "sent to the booker. Untick for runs that owe no distributor royalty, "
        "such as a Classic Movie Night; they still appear in the owner's summary.",
    )

    # TODO: Validation that an 3d engagement can't be book on non 3d screens

    status = models.CharField(
        max_length=20, choices=EngagementStatus.choices, default=EngagementStatus.DRAFT
    )

    notes = models.TextField(blank=True)
    admissions = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total tickets sold for this run (from Square sales data). "
        "Admin-only; not shown publicly.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date"]
        indexes = [
            models.Index(fields=["start_date", "end_date"]),
        ]
        verbose_name = "Engagement"
        verbose_name_plural = "Engagements"

    def __str__(self) -> str:
        return f"{self.display_title} ({self.start_date} → {self.end_date})"

    @property
    def is_active(self) -> bool:
        today = timezone.localdate()
        return (
            self.status == EngagementStatus.CONFIRMED
            and self.start_date <= today <= self.end_date
        )

    @property
    def ordered_films(self) -> list[Film]:
        return [ef.film for ef in self.engagement_films.all()]

    @property
    def primary_film(self) -> Film | None:
        films = self.ordered_films
        return films[0] if films else None

    @property
    def total_runtime_minutes(self) -> int:
        return sum(
            f.runtime_minutes or self.UNKNOWN_RUNTIME_MINUTES
            for f in self.ordered_films
        )

    @property
    def display_title(self) -> str:
        if self.event_title:
            return self.event_title
        return " + ".join(f.title for f in self.ordered_films)

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Cascade only on the move into CANCELLED, so a later save of a
        # cancelled run (a notes fix) leaves showtimes staff re-enabled alone.
        was = (
            Engagement.objects.filter(pk=self.pk)
            .values_list("status", flat=True)
            .first()
            if self.pk
            else None
        )
        super().save(*args, **kwargs)
        if self.status == EngagementStatus.CANCELLED and was != self.status:
            self.cancel_upcoming_showtimes()

    def cancel_upcoming_showtimes(self) -> int:
        """Cancel every showtime of this run that has not started yet.

        A cancelled run's showtimes would otherwise still hold their screen
        slots, blocking whatever is booked in their place. Past showtimes
        happened and are left alone. Setting the run back to Confirmed does
        not restore them; staff re-enable showtimes one by one.
        """
        return self.showtimes.filter(
            is_cancelled=False, starts_at__gte=timezone.now()
        ).update(is_cancelled=True)

    def clean(self) -> None:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("end_date cannot be before start_date.")

    @classmethod
    def default_visibility_for(cls, kind: str) -> bool:
        return kind == cls.Kind.REGULAR
