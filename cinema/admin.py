# cinema/admin.py
# mypy: disable-error-code="type-arg"
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import path

from .forms import StudioCatalogImportForm
from .studio_import import (
    StudioImportError,
    get_or_create_studio,
    import_rows,
    preview,
    read_upload,
)

from .models import (
    Engagement,
    EngagementFilm,
    Film,
    Screen,
    Showtime,
    SponsorshipInquiry,
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
    list_filter = (
        "status",
        "presentation_format",
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
    list_display = ("title", "rating", "runtime_minutes", "review", "created_at")
    search_fields = ("title", "tmdb_id", "imdb_id", "slug")
    list_filter = ("rating",)
    prepopulated_fields = {"slug": ("title",)}
    # Reviews are linked from the post editor in the dashboard, which is also
    # the only place blog posts can be searched now.
    readonly_fields = ("review",)


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
    change_list_template = "admin/cinema/studiotitle/change_list.html"
    list_display = (
        "title", "studio", "release_date", "mpa_rating",
        "runtime_minutes", "is_available",
    )
    list_filter = ("studio", "is_available", "mpa_rating")
    list_editable = ("is_available",)
    search_fields = ("title", "original_title")
    autocomplete_fields = ("film",)
    readonly_fields = ("imported_at", "updated_at")

    def get_urls(self):
        return [
            path(
                "import-catalog/",
                self.admin_site.admin_view(self.import_catalog),
                name="cinema_studiotitle_import_catalog",
            ),
            *super().get_urls(),
        ]

    def import_catalog(self, request: HttpRequest) -> HttpResponse:
        """Upload a studio's availability list.

        The browser half of `manage.py import_studio_catalog` — same reader,
        same writer, same idempotence. Adding titles is what this does, so it
        asks for the add permission rather than staff alone.
        """
        if not self.has_add_permission(request):
            raise PermissionDenied

        form = StudioCatalogImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            result = self._run_import(request, form)
            if result is not None:
                return redirect("admin:cinema_studiotitle_changelist")

        return render(
            request,
            "admin/cinema/studiotitle/import_catalog.html",
            {
                **self.admin_site.each_context(request),
                "title": "Import catalog",
                "form": form,
                "opts": self.opts,
            },
        )

    def _run_import(self, request: HttpRequest, form: StudioCatalogImportForm):
        """Read the upload and write it, or hang the failure on the form."""
        data = form.cleaned_data
        try:
            rows = read_upload(data["file"], data["sheet"])
        except StudioImportError as error:
            form.add_error("file", str(error))
            return None

        if not rows:
            form.add_error("file", "No titles in that file.")
            return None

        if data["dry_run"]:
            result = preview(rows)
            titles = result.rows_read - result.collapsed
            self.message_user(
                request,
                f"Preview: {titles} title{'' if titles == 1 else 's'} from "
                f"{result.rows_read} rows ({result.collapsed} variants "
                f"collapsed). Nothing was written.",
                messages.WARNING,
            )
            return result

        with transaction.atomic():
            studio = get_or_create_studio(data["studio"])
            result = import_rows(studio, rows)

        self.message_user(
            request,
            f"{studio.name}: {result.created} created, {result.updated} "
            f"updated, {result.collapsed} variants collapsed, "
            f"{result.rows_read} rows read.",
            messages.SUCCESS,
        )
        return result


@admin.register(SponsorshipInquiry)
class SponsorshipInquiryAdmin(admin.ModelAdmin):
    list_display = (
        "business_name", "contact_name", "email", "tier", "status", "created_at",
    )
    list_filter = ("status", "tier")
    search_fields = ("business_name", "contact_name", "email")
    readonly_fields = ("created_at", "ip")
