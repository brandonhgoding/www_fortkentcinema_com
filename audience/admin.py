from django.contrib import admin
from django.http import HttpRequest

from .models import Subscriber, SubscriptionChange


class SubscriptionChangeInline(admin.TabularInline):
    """The subscriber's opt-in and opt-out history, read-only: it is a
    record of what happened, written by Subscriber.save()."""

    model = SubscriptionChange
    extra = 0
    fields = ("status", "at")
    readonly_fields = ("status", "at")
    can_delete = False

    def has_add_permission(
        self, request: HttpRequest, obj: Subscriber | None = None
    ) -> bool:
        return False


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "status", "source", "consent_at")
    list_filter = ("status", "source")
    search_fields = ("email",)
    # confirmed_at is the CAN-SPAM consent record; staff must not edit it.
    readonly_fields = (
        "unsubscribe_token",
        "consent_at",
        "confirmed_at",
        "confirmation_sent_at",
    )
    inlines = [SubscriptionChangeInline]
