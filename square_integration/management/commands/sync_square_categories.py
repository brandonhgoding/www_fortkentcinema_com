from django.core.management.base import BaseCommand
from square_integration.services.square_client import get_square_client
from square_integration.services.square_categories import build_categories_list


class Command(BaseCommand):
    help = "Ensure the 'Memberships' Category exists in Square and print its ID."

    def handle(self, *args, **opts):
        build_categories_list()
        self.stdout.write(self.style.SUCCESS(f"Categories synchronized successfully."))
