from django.core.management.base import BaseCommand
from square_integration.services.square_memberships import build_membership_catalog_items


class Command(BaseCommand):
    help = "Ensure the 'Memberships' exitst in Square Catalog"

    def handle(self, *args, **opts):
        build_membership_catalog_items()
        self.stdout.write(self.style.SUCCESS(f"Categories synchronized successfully."))
