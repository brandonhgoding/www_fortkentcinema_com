# cinema/admin.py
# mypy: disable-error-code="type-arg"
from django.contrib import admin

from .models import (
    Engagement,
    EngagementFilm,
    Film,
    Screen,
    Showtime,
    Studio,
    StudioTitle,
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
        "display_title",
        "screen",
        "start_date",
        "end_date",
        "status",
        "admissions",
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
    list_display = ("title", "rating", "runtime_minutes", "review", "created_at")
    search_fields = ("title", "tmdb_id", "imdb_id", "slug")
    list_filter = ("rating",)
    prepopulated_fields = {"slug": ("title",)}
    # Link a film to our own review of it. `manage.py link_film_reviews` handles
    # the obvious "A Review of <Film>" matches; this is for the rest.
    autocomplete_fields = ("review",)


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity")


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "catalog_updated")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(StudioTitle)
class StudioTitleAdmin(admin.ModelAdmin):
    list_display = (
        "title", "studio", "release_date", "mpa_rating",
        "runtime_minutes", "is_available",
    )
    list_filter = ("studio", "is_available", "mpa_rating")
    list_editable = ("is_available",)
    search_fields = ("title", "original_title")
    autocomplete_fields = ("film",)
    readonly_fields = ("imported_at", "updated_at")
