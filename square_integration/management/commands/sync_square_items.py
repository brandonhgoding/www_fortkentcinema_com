from django.core.management.base import BaseCommand
from square_integration.services.square_items import build_square_catalog_items


class Command(BaseCommand):
    help = "Ensure the 'Items' Category exists in Square and print its ID."

    def handle(self, *args, **opts):
        build_square_catalog_items()
        self.stdout.write(self.style.SUCCESS(f"Items synchronized successfully."))
