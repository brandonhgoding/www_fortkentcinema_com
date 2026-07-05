# cinema/admin.py
# mypy: disable-error-code="type-arg"
from django.contrib import admin

from .models import Engagement, EngagementFilm, Film, Screen, Showtime


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
        "display_title",
        "screen",
        "start_date",
        "end_date",
        "status",
        "presentation_format",
    )
    list_filter = ("status", "presentation_format")
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
    search_fields = ("title", "tmdb_id", "imdb_id")
    list_filter = ("rating",)


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity")
