from django.core.management.base import BaseCommand
from django.utils import timezone

from tickets.orders import expire_stale


class Command(BaseCommand):
    help = "Expire online ticket orders left unpaid past the hold, after asking Square."

    def handle(self, *args, **options) -> None:
        count = expire_stale(timezone.now())
        self.stdout.write(f"Expired {count} order(s)")
