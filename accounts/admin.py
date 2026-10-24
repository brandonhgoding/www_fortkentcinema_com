from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

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
