from django.contrib import admin
from django.utils.html import format_html

from .models import CallLog, Voicemail


class VoicemailInline(admin.TabularInline):
    model = Voicemail
    extra = 0
    fields = ("created_at", "status", "transcript")
    readonly_fields = ("created_at", "transcript")
    show_change_link = True


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ("caller", "started_at", "choices_display")
    search_fields = ("caller", "call_sid")
    date_hierarchy = "started_at"
    readonly_fields = ("call_sid", "caller", "called", "started_at", "choices")
    inlines = [VoicemailInline]

    @admin.display(description="Menu choices")
    def choices_display(self, obj: CallLog) -> str:
        return ", ".join(obj.choices) or "—"


@admin.register(Voicemail)
class VoicemailAdmin(admin.ModelAdmin):
    list_display = ("caller", "created_at", "status", "duration_seconds", "excerpt")
    list_filter = ("status", "transcription_status")
    list_editable = ("status",)
    search_fields = ("caller", "transcript")
    readonly_fields = (
        "call",
        "recording_sid",
        "caller",
        "recording_link",
        "duration_seconds",
        "transcript",
        "transcription_status",
        "created_at",
    )
    exclude = ("recording_url",)

    @admin.display(description="Transcript")
    def excerpt(self, obj: Voicemail) -> str:
        if not obj.transcript:
            return "—"
        return obj.transcript[:80] + ("…" if len(obj.transcript) > 80 else "")

    @admin.display(description="Recording")
    def recording_link(self, obj: Voicemail) -> str:
        if not obj.audio_url:
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Listen</a>', obj.audio_url
        )
