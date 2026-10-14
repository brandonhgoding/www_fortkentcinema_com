# cinema/admin.py
# mypy: disable-error-code="type-arg"
from django.contrib import admin

from .models import (
    AdInquiry,
    Engagement,
    EngagementFilm,
    Film,
    RentalInquiry,
    Screen,
    Showtime,
)


class EngagementFilmInline(admin.TabularInline):
    model = EngagementFilm
    extra = 1
    ordering = ("position",)


class ShowtimeInline(admin.TabularInline):
    model = Showtime
    extra = 0


@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    inlines = (EngagementFilmInline, ShowtimeInline)
    list_display = (
        "title",
        "screen",
        "start_date",
        "end_date",
        "status",
        "admissions",
        "presentation_format",
        "language",
        "translation",
    )
    list_filter = (
        "status",
        "presentation_format",
        "language",
        "translation",
        "is_free_for_members",
        "in_ticket_report",
    )
    search_fields = ("engagement_films__film__title",)
    date_hierarchy = "start_date"


@admin.register(Showtime)
class ShowtimeAdmin(admin.ModelAdmin):
    list_display = (
        "engagement",
        "screen",
        "starts_at",
        "is_cancelled",
        "captions",
    )
    list_filter = ("screen", "is_cancelled", "captions")
    search_fields = ("engagement__engagement_films__film__title",)
    date_hierarchy = "starts_at"


@admin.register(Film)
class FilmAdmin(admin.ModelAdmin):
    list_display = ("title", "rating", "runtime_minutes", "created_at")
    search_fields = ("title", "tmdb_id", "imdb_id", "slug")
    list_filter = ("rating",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity")


@admin.register(RentalInquiry)
class RentalInquiryAdmin(admin.ModelAdmin):
    list_display = (
        "contact_name", "email", "preferred_date", "guests", "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("contact_name", "email", "event_type")
    readonly_fields = ("created_at", "ip")


@admin.register(AdInquiry)
class AdInquiryAdmin(admin.ModelAdmin):
    list_display = (
        "business_name", "contact_name", "email", "ad_type", "status",
        "created_at",
    )
    list_filter = ("status", "ad_type")
    search_fields = ("business_name", "contact_name", "email")
    readonly_fields = ("created_at", "ip")
