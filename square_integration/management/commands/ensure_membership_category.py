from django.core.management.base import BaseCommand
from square_integration.services.square_client import get_square_client
from square_integration.services.square_categories import ensure_memberships_category


class Command(BaseCommand):
    help = "Ensure the 'Memberships' Category exists in Square and print its ID."

    def handle(self, *args, **opts):
        client = get_square_client()
        cat_id = ensure_memberships_category(client, "Memberships")
        self.stdout.write(self.style.SUCCESS(f"Memberships category ID: {cat_id}"))
