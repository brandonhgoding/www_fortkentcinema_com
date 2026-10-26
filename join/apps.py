from django.apps import AppConfig


class JoinConfig(AppConfig):
    name = "join"
    verbose_name = "Membership checkout"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # The box office ledger never imports this app; it tells the ledger
        # who buys its orders here instead.
        from boxoffice.memberships import register_order_source

        from join.source import SOURCE

        register_order_source(SOURCE)
