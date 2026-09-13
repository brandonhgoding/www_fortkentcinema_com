from django.contrib import admin

from .models import (
    Member,
    MembershipBenefit,
    MembershipTerm,
    MembershipTier,
    Subscriber,
)


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "status", "source", "consent_at")
    list_filter = ("status", "source")
    search_fields = ("email",)
    readonly_fields = ("unsubscribe_token", "consent_at")


@admin.register(MembershipTier)
class MembershipTierAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "price", "show_on_membership_page", "sort_order")
    list_filter = ("show_on_membership_page", "featured", "is_family_tier")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("benefits",)

    def get_readonly_fields(self, request, obj=None):
        # The slug is load-bearing outside this database: Square's payment
        # dashboard redirects to /thanks?tier=<slug> and the Join button's
        # GA4 tracking carries it too. Editing it after creation would break
        # revenue attribution silently, with the page still rendering fine
        # — so it is only ever editable (via prepopulated_fields) on add.
        return ("slug",) if obj else ()


@admin.register(MembershipBenefit)
class MembershipBenefitAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    search_fields = ("name",)


class MembershipTermInline(admin.TabularInline):
    model = MembershipTerm
    extra = 0


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "email", "phone")
    search_fields = ("last_name", "first_name", "email")
    inlines = [MembershipTermInline]
