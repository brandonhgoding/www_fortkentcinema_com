from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"
    # AutoField, not the project's BigAutoField: auth_user.id is a 32-bit
    # serial and the migration must match the column that already exists.
    default_auto_field = "django.db.models.AutoField"
