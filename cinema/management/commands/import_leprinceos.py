from cinema.leprinceos_import import import_all
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Import films/engagements/showtimes from the leprinceos API into the cinema tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true",
            help="Required. Wipe the cinema tables and rebuild from the API.",
        )
        parser.add_argument("--base-url", default=settings.LEPRINCEOS_BASE_URL)
        parser.add_argument("--capacity", type=int, default=1)

    def handle(self, *args, **options):
        if not options["flush"]:
            raise CommandError(
                "This command wipes and rebuilds the cinema tables. "
                "Re-run with --flush to proceed."
            )
        counts = import_all(
            options["base_url"], flush=True, capacity_default=options["capacity"]
        )
        summary = ", ".join(f"{k}={v}" for k, v in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Imported: {summary}"))
