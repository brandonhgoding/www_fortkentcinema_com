from django.contrib import admin

from .models import Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "status", "source", "consent_at")
    list_filter = ("status", "source")
    search_fields = ("email",)
    readonly_fields = ("unsubscribe_token", "consent_at")
