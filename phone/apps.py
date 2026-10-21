from django.apps import AppConfig


class PhoneConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "phone"

    def ready(self) -> None:
        from phone import checks  # noqa: F401  registers the system check
