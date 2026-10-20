from django.apps import AppConfig


class BoxofficeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "boxoffice"
    verbose_name = "Box Office"

    def ready(self) -> None:
        from boxoffice import checks  # noqa: F401  registers the system check
