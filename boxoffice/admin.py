# mypy: disable-error-code="type-arg"
from django.contrib import admin

from .models import EmailRecipient, EmailReport, MembershipSale, SalesPull


class EmailRecipientInline(admin.TabularInline):
    model = EmailRecipient
    extra = 1


@admin.register(EmailReport)
class EmailReportAdmin(admin.ModelAdmin):
    list_display = ("kind", "subject", "enabled")
    inlines = [EmailRecipientInline]


@admin.register(SalesPull)
class SalesPullAdmin(admin.ModelAdmin):
    list_display = (
        "business_date",
        "status",
        "orders",
        "lines",
        "missing_online",
        "owner_email_sent",
        "report_email_sent",
    )
    readonly_fields = (
        "business_date",
        "started_at",
        "finished_at",
        "status",
        "orders",
        "lines",
        "missing_online",
        "owner_email_sent",
        "report_email_sent",
        "error",
    )

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(MembershipSale)
class MembershipSaleAdmin(admin.ModelAdmin):
    list_display = ("order_id", "paid_at", "tier", "email", "status")
    list_filter = ("status",)
    search_fields = ("order_id", "email", "display_name")
    readonly_fields = (
        "order_id",
        "paid_at",
        "tier",
        "quantity",
        "gross_cents",
        "display_name",
        "email",
        "phone",
        "status",
        "error",
        "term",
        "created_at",
        "processed_at",
    )

    def has_add_permission(self, request, obj=None) -> bool:
        return False
