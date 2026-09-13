from django.contrib import admin

from .models import Member, MembershipTerm, Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "status", "source", "consent_at")
    list_filter = ("status", "source")
    search_fields = ("email",)
    readonly_fields = ("unsubscribe_token", "consent_at")


class MembershipTermInline(admin.TabularInline):
    model = MembershipTerm
    extra = 0


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "email", "phone")
    search_fields = ("last_name", "first_name", "email")
    inlines = [MembershipTermInline]
