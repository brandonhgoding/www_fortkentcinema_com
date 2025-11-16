import uuid
from decimal import Decimal
from typing import Any
from datetime import datetime, time, timedelta

from django.db import models
from django.db.models import CheckConstraint, Q
from django.urls import reverse
from django.utils import timezone

from core.mixins import SlugModelMixin


class RateTypes(models.TextChoices):
    EVENING_ADMISSION = "EA", "Evening Admission"
    MATINEE = ("MT", "Matinee Admission")


class TicketRate(models.Model):
    rate_type = models.CharField(
        max_length=2, choices=RateTypes.choices, default=RateTypes.EVENING_ADMISSION, unique=True
    )
    price = models.DecimalField(max_digits=6, decimal_places=2)
    member_price = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.get_rate_type_display()}: ${self.price}"

    def get_rate_type_display(self) -> str:
        return dict(RateTypes.choices).get(self.rate_type, "Unknown")

    def get_member_discount_amount(self) -> Decimal | None:
        if self.member_price is not None:
            return self.price - self.member_price
        return None


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
    description = models.TextField(blank=True, null=True)
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
    class AuditoriumChoices(models.TextChoices):
        SOUTH_AUDITORIUM = "South Auditorium", "South Auditorium"
        NORTH_AUDITORIUM = "North Auditorium", "North Auditorium"

        @property
        def capacity(self) -> int:
            capacities = {
                self.SOUTH_AUDITORIUM: 100,
                self.NORTH_AUDITORIUM: 100,
            }
            return capacities.get(self, 0)

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
    auditorium = models.CharField(
        max_length=16, choices=AuditoriumChoices.choices, default=AuditoriumChoices.SOUTH_AUDITORIUM
    )
    square_id = models.CharField(max_length=255, blank=True, null=True, editable=False)
    square_version = models.BigIntegerField(blank=True, null=True, editable=False)

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

    @property
    def showtime_list(self):
        from collections import defaultdict
        from django.utils.timezone import now, make_aware, get_current_timezone

        grouped_times = defaultdict(list)
        current_datetime = now()
        max_date = current_datetime.date() + timedelta(days=6)  # Calculate the maximum allowed date
        tz = get_current_timezone()  # Get the current timezone

        for screening in self.screening_times.all():
            screening_datetime = datetime.combine(screening.date, screening.time)
            if timezone.is_naive(screening_datetime):  # Check if naive
                screening_datetime = make_aware(
                    screening_datetime, timezone=tz
                )  # Make it timezone-aware
            if (
                current_datetime
                <= screening_datetime
                <= datetime.combine(max_date, time.max, tzinfo=tz)
            ):
                formatted_time = screening.time.strftime("%I:%M %p").lstrip(
                    "0"
                )  # Format time as "1:00 PM"
                grouped_times[screening.date].append(formatted_time)

        # Convert defaultdict to a list of dictionaries
        return [{"date": date, "times": times} for date, times in grouped_times.items()]

    class Meta:
        ordering = ["booking_start_date"]


class ScreeningTime(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="screening_times")
    date = models.DateField()
    time = models.TimeField()
    square_variation_id = models.CharField(max_length=255, blank=True, null=True, editable=False)
    square_variation_version = models.BigIntegerField(blank=True, null=True, editable=False)

    def __str__(self) -> str:
        return self.screening_time_string

    @property
    def screening_time_string(self) -> str:
        return f"{self.booking.film.title} on {self.date} at {self.time}"

    @property
    def ticket_rate(self) -> int:
        if self.is_matinee:
            return 800
        return 1200

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


class Ticket(models.Model):
    screening_time = models.ForeignKey(
        ScreeningTime, on_delete=models.RESTRICT, related_name="tickets"
    )
    rate = models.ForeignKey(TicketRate, on_delete=models.CASCADE)
    ticket_number = models.CharField(max_length=20, unique=True)
