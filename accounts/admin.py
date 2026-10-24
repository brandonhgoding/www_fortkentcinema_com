from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils import timezone

from .models import User


class EmailUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email",)


class EmailUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ("email",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = EmailUserCreationForm
    form = EmailUserChangeForm
    ordering = ("email",)
    list_display = ("email", "is_staff", "email_verified_at")
    readonly_fields = ("email_verified_at",)
    search_fields = ("email",)
    actions = ["mark_email_verified"]

    def save_model(self, request, obj, form, change) -> None:
        # Accounts the owner makes or promotes are trusted, so the nightly
        # cleanup of unverified accounts never touches them.
        if obj.email_verified_at is None and (not change or obj.is_staff):
            obj.email_verified_at = timezone.now()
        super().save_model(request, obj, form, change)

    @admin.action(description="Mark email verified")
    def mark_email_verified(self, request, queryset) -> None:
        count = queryset.filter(email_verified_at__isnull=True).update(
            email_verified_at=timezone.now()
        )
        self.message_user(request, f"Marked {count} users verified.")
    # The base groups, with email moved up to the login and "Personal info"
    # dropped: the user stores no names.
    fieldsets = (
        (None, {"fields": ("email", "password", "email_verified_at")}),
        *BaseUserAdmin.fieldsets[2:],
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
