from django.apps import AppConfig


class TicketsConfig(AppConfig):
    name = "tickets"
    verbose_name = "Online tickets"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # The box office ledger and webhook never import this app; it tells
        # them about itself here instead.
        from boxoffice.payment_events import register_payment_handler
        from boxoffice.pull import register_website

        from tickets.ledger import TicketOrders
        from tickets.orders import handle_square_payment

        register_payment_handler(handle_square_payment)
        register_website(TicketOrders())
