# mypy: disable-error-code="type-arg"
from django.contrib import admin

from .models import MembershipOrder


@admin.register(MembershipOrder)
class MembershipOrderAdmin(admin.ModelAdmin):
    """Read-mostly: orders are made by the join page, never by hand."""

    list_display = ("number", "created_at", "status", "tier", "first_name",
                    "last_name", "email", "total_dollars")
    list_filter = ("status", "tier")
    search_fields = ("number", "email", "first_name", "last_name",
                     "square_order_id")
    readonly_fields = ("number", "token", "square_order_id", "square_payment_id",
                       "square_checkout_url", "square_customer_id", "created_at",
                       "paid_at", "term", "sale")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False
