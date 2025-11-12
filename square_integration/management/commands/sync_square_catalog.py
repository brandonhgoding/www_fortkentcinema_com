# cinema/management/commands/sync_square_categories.py

from django.core.management.base import BaseCommand
from square_integration.services.square_catalog import sync_categories_to_square


class Command(BaseCommand):
    help = "Sync Django Category objects to Square Catalog categories."

    def handle(self, *args, **options):
        sync_categories_to_square()
        self.stdout.write(self.style.SUCCESS("Square categories sync completed."))
