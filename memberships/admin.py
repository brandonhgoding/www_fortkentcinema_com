from memberships.models import MembershipType, MembershipBenefit
from django.contrib import admin, messages
from square_integration.services.square_memberships import build_membership_catalog_items


@admin.action(description="Sync membership items to Square")
def sync_square_membership_items(modeladmin, request, queryset):
    """
    Admin action to (re)synchronize membership items in Square.

    Note: currently ignores `queryset` and syncs all active MembershipType
    records, because that's what `build_membership_catalog_items()` does.
    """
    try:
        build_membership_catalog_items()
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


@admin.register(MembershipType)
class MembershipType(admin.ModelAdmin):
    actions = [sync_square_membership_items]


admin.site.register(MembershipBenefit)
