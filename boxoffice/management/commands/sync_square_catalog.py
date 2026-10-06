from boxoffice.gateway import disabled_reason, get_gateway
from boxoffice.sync import reconcile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Bring Square ticket items in line with confirmed engagements."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change without writing.")

    def handle(self, *args, **options) -> None:
        gateway = get_gateway()
        if gateway is None:
            self.stdout.write(f"Square sync disabled ({disabled_reason()})")
            return
        dry_run = options["dry_run"]
        report = reconcile(timezone.localdate(), gateway, dry_run=dry_run)
        self.stdout.write(
            f"{'Would push' if dry_run else 'Pushed'} {len(report.pushed)}")
        self.stdout.write(
            f"{'Would delete' if dry_run else 'Deleted'} {len(report.deleted)}")
        self.stdout.write(
            f"{'Would attach' if dry_run else 'Attached'} {len(report.images)} "
            f"poster{'' if len(report.images) == 1 else 's'}")
        if report.image_skips:
            self.stdout.write("Posters skipped: " + "; ".join(report.image_skips))
        if report.unknown_items:
            self.stdout.write("Unknown items in ticket category: "
                              + ", ".join(report.unknown_items))
        for error in report.errors:
            self.stdout.write(f"ERROR: {error}")
        if report.errors:
            raise CommandError(f"{len(report.errors)} error(s) during reconcile")
