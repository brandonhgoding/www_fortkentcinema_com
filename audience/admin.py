from typing import cast

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import (
    MembershipLinkRequest,
    FreeAdmission,
    Member,
    MembershipBenefit,
    MembershipTerm,
    MembershipTier,
    Subscriber,
    SubscriptionChange,
)


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


@admin.register(MembershipTier)
class MembershipTierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "price",
        "free_admissions_per_month",
        "square_variation_id",
        "show_on_membership_page",
        "sort_order",
    )
    list_filter = ("show_on_membership_page", "featured", "is_family_tier")
    search_fields = ("name", "slug")
    filter_horizontal = ("benefits",)

    # The slug is load-bearing outside this database: Square's payment
    # dashboard redirects to /thanks?tier=<slug> and the Join button's GA4
    # tracking carries it too. Editing it after creation would break revenue
    # attribution silently, with the page still rendering fine. So it is
    # editable only while adding, and auto-filled from the name there.
    #
    # Both methods below must agree: prepopulating a field that is readonly
    # raises KeyError when the form renders, because a readonly field is not
    # in the form at all.
    def get_readonly_fields(self, request, obj=None):
        return ("slug",) if obj else ()

    def get_prepopulated_fields(self, request, obj=None):
        return {} if obj else {"slug": ("name",)}


@admin.register(MembershipBenefit)
class MembershipBenefitAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    search_fields = ("name",)


@admin.register(FreeAdmission)
class FreeAdmissionAdmin(admin.ModelAdmin):
    list_display = ("member", "redeemed_on", "recorded_by")
    list_select_related = ("member", "recorded_by")
    search_fields = ("member__first_name", "member__last_name", "member__email")
    date_hierarchy = "redeemed_on"
    autocomplete_fields = ("member",)


class MembershipTermInline(admin.TabularInline):
    model = MembershipTerm
    extra = 0

    def get_queryset(self, request: HttpRequest) -> QuerySet[MembershipTerm]:
        # Each row is labelled with MembershipTerm.__str__, which names the
        # tier: one query per term without this.
        return cast(
            "QuerySet[MembershipTerm]",
            super().get_queryset(request).select_related("tier"),
        )


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "email")
    search_fields = ("last_name", "first_name", "email")
    inlines = [MembershipTermInline]


@admin.register(MembershipLinkRequest)
class MembershipLinkRequestAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "user", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("first_name", "last_name", "user__email")
    readonly_fields = ("created_at", "resolved_at")
