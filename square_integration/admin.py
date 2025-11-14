from django.contrib import admin, messages
from square_integration.models import CatalogCategory, TaxRate
from square_integration.services.square_categories import build_categories_list


@admin.action(description="Sync Category to Square")
def sync_square_category(modeladmin, request, queryset):
    """
    Admin action to (re)synchronize membership items in Square.

    Note: currently ignores `queryset` and syncs all active MembershipType
    records, because that's what `build_membership_catalog_items()` does.
    """
    try:
        build_categories_list()
    except Exception as exc:
        modeladmin.message_user(
            request,
            f"Error syncing membership items to Square: {exc}",
            level=messages.ERROR,
        )
    else:
        modeladmin.message_user(
            request,
            "Membership items successfully synced to Square.",
            level=messages.SUCCESS,
        )


@admin.register(CatalogCategory)
class CatalogCategoryAdmin(admin.ModelAdmin):
    actions = [sync_square_category]

admin.site.register(TaxRate)
