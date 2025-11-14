from django.contrib import admin, messages
from inventory.models import InventoryItem
from square_integration.services.square_items import build_square_catalog_items


@admin.action(description="Sync Items to Square")
def sync_square_catalog_items(modeladmin, request, queryset):
    """
    Admin action to (re)synchronize membership items in Square.

    Note: currently ignores `queryset` and syncs all active MembershipType
    records, because that's what `build_membership_catalog_items()` does.
    """
    try:
        build_square_catalog_items()
    except Exception as exc:
        modeladmin.message_user(
            request,
            f"Error syncing items to Square: {exc}",
            level=messages.ERROR,
        )
    else:
        modeladmin.message_user(
            request,
            "Items successfully synced to Square.",
            level=messages.SUCCESS,
        )


@admin.register(InventoryItem)
class CatalogItemAdmin(admin.ModelAdmin):
    actions = [sync_square_catalog_items]
