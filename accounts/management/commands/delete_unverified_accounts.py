from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

GRACE = timedelta(days=7)


class Command(BaseCommand):
    help = "Delete member accounts whose email was never verified within 7 days."

    def handle(self, *args, **options) -> None:
        stale = get_user_model().objects.filter(
            is_staff=False,
            email_verified_at__isnull=True,
            date_joined__lt=timezone.now() - GRACE,
        )
        # delete() totals cascaded rows too; report only the accounts.
        _, per_model = stale.delete()
        count = per_model.get("accounts.User", 0)
        self.stdout.write(f"Deleted {count} unverified accounts.")
