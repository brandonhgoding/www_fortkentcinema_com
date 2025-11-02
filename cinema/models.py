import uuid
from typing import Any
from datetime import datetime, time

from django.db import models
from django.db.models import CheckConstraint, Q
from django.urls import reverse
from django.utils import timezone

from core.mixins import SlugModelMixin


class RateTypes(models.TextChoices):
    GENERAL_ADMISSION = "GA", "General Admission"
    MATINEE = "MT", "Matinee"
    SPECIAL_EVENT_SCREENING = "SE", "Special Event Screening"
    DOUBLE_FEATURE = "DF", "Double Feature"


class TicketRate(models.Model):
    rate_type = models.CharField(
        max_length=2, choices=RateTypes.choices, default=RateTypes.GENERAL_ADMISSION, unique=True
    )
    price = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.get_rate_type_display()}: ${self.price}"

    def get_rate_type_display(self) -> str:
        return dict(RateTypes.choices).get(self.rate_type, "Unknown")


class FilmRating(models.TextChoices):
    G = "G", "General Audiences"
    PG = "PG", "Parental Guidance Suggested"
    PG13 = "PG-13", "Parents Strongly Cautioned"
    R = "R", "Restricted"
    NC17 = "NC-17", "Adults Only"


class FilmGenre(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ["name"]


class Film(SlugModelMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=100)
    imdb_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    youtube_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    rating = models.CharField(max_length=5, choices=FilmRating.choices, default=FilmRating.PG)
    genres = models.ManyToManyField(FilmGenre, related_name="films", blank=True)
    runtime = models.PositiveIntegerField(help_text="Runtime in minutes", blank=True, null=True)
    poster_url = models.URLField(max_length=200, blank=True, null=True)

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self):
        return reverse("website:film_detail", kwargs={"slug": self.slug})

    class Meta:
        ordering = ["title"]


class Booking(models.Model):
    film = models.ForeignKey(Film, on_delete=models.CASCADE, related_name="bookings")
    booking_start_date = models.DateField()
    booking_end_date = models.DateField()
    confirmed = models.BooleanField(default=False)
    # percentage: a share of gross, e.g., 50.00 => 50%
    terms_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text="0–100"
    )
    # guarantee: flat minimum payout (assume currency in site settings)
    terms_guarantee = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        constraints = [
            CheckConstraint(
                name="booking_terms_percentage_range",
                check=Q(terms_percentage__gte=0) & Q(terms_percentage__lte=100),
            ),
            CheckConstraint(
                name="booking_terms_guarantee_nonneg",
                check=Q(terms_guarantee__gte=0),
            ),
        ]

    # def settlement_minimum(self, gross_revenue):
    #     """
    #     Returns the minimum owed for this booking based on terms.
    #     gross_revenue: Decimal
    #     """
    #     pct_amount = (self.terms_percentage / 100) * gross_revenue
    #     return max(pct_amount, self.terms_guarantee)

    def __str__(self) -> str:
        return (
            f"Booking for {self.film.title} from {self.booking_start_date}"
            f" to {self.booking_end_date}"
        )

    @property
    def is_active(self) -> bool:
        return self.booking_start_date <= timezone.now().date() <= self.booking_end_date

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed

    class Meta:
        ordering = ["booking_start_date"]


class ScreeningTime(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="screening_times")
    date = models.DateField()
    time = models.TimeField()

    def __str__(self) -> str:
        return f"{self.booking.film.title} on {self.date} at {self.time}"

    @property
    def is_matinee(self) -> bool:
        if isinstance(self.time, str):
            show_time = datetime.strptime(self.time, "%H:%M:%S").time()
        else:
            show_time = self.time
        return show_time < time(16, 0)

    class Meta:
        unique_together = ("booking", "date", "time")
        ordering = ["date", "time"]


class Event(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    event_start_date = models.DateField()
    event_end_date = models.DateField()
    slug_field = "name"

    def __str__(self) -> str:
        return f"{self.name} on {self.event_start_date} to {self.event_end_date}"

    class Meta:
        ordering = ["-event_start_date"]
        verbose_name = "Event"
        verbose_name_plural = "Events"

    slug = models.SlugField(max_length=100, blank=True, null=True)
