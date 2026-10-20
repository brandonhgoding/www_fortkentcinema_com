# mypy: disable-error-code="type-arg"
from django.contrib import admin

from .models import TicketLine, TicketOrder


class TicketLineInline(admin.TabularInline):
    model = TicketLine
    extra = 0


@admin.register(TicketOrder)
class TicketOrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "created_at",
        "status",
        "showtime",
        "first_name",
        "last_name",
        "email",
        "total_dollars",
    )
    list_filter = ("status",)
    search_fields = ("number", "first_name", "last_name", "email")
    readonly_fields = (
        "number",
        "token",
        "square_order_id",
        "square_payment_id",
        "square_checkout_url",
        "created_at",
        "paid_at",
        "refunded_at",
    )
    date_hierarchy = "created_at"
    inlines = [TicketLineInline]
