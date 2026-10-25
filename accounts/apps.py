from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"
    # AutoField, not the project's BigAutoField: auth_user.id is a 32-bit
    # serial and the migration must match the column that already exists.
    default_auto_field = "django.db.models.AutoField"

    def ready(self) -> None:
        from django.contrib.auth.signals import user_login_failed

        from accounts import lockout

        user_login_failed.connect(
            lockout.record_failed_login, dispatch_uid="accounts.lockout.ip_failures"
        )
