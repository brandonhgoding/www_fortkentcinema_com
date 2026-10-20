import datetime
import logging

from boxoffice.gateway import GatewayError, disabled_reason, get_gateway
from boxoffice.models import SalesPull
from boxoffice.pull import EASTERN, day_orders, pull_day
from boxoffice.reports import owner_summary, render_report, send_reports, ticket_report
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Pull recent Square sales into the ledger and email the daily reports."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--date", type=datetime.date.fromisoformat,
                            help="Last day to pull, YYYY-MM-DD (default: today).")
        parser.add_argument("--days", type=int, default=3,
                            help="How many days to pull, ending on --date (default 3).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would be stored; write and send nothing.")
        parser.add_argument("--no-email", action="store_true",
                            help="Pull sales but do not send the report emails.")

    def handle(self, *args, **options) -> None:
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be at least 1")
        gateway = get_gateway()
        if gateway is None:
            self.stdout.write(f"Square sync disabled ({disabled_reason()})")
            return
        target = options["date"] or datetime.datetime.now(EASTERN).date()
        window = [target - datetime.timedelta(days=n) for n in range(days - 1, -1, -1)]
        if options["dry_run"]:
            self.dry_run(window, target, gateway)
        else:
            self.pull(window, target, gateway, send_email=not options["no_email"])

    def dry_run(self, window, target, gateway) -> None:
        for day in window:
            try:
                orders = day_orders(day, gateway)
            except GatewayError as exc:
                self.stdout.write(f"ERROR: {exc}")
                raise CommandError(f"Dry run failed for {day}") from exc
            lines = sum(len(o.lines) for o in orders)
            self.stdout.write(
                f"Would store {lines} lines from {len(orders)} orders for {day}")
        for kind, rows in (("OWNER_SUMMARY", owner_summary(target)),
                           ("TICKET_REPORT", ticket_report(target))):
            self.stdout.write(f"--- {kind} for {target} (ledger as it stands) ---")
            self.stdout.write(render_report(kind, target, rows))

    def pull(self, window, target, gateway, *, send_email: bool) -> None:
        failed = []
        target_pull = None
        for day in window:
            pull = pull_day(day, gateway)
            if pull.status == SalesPull.Status.FAILED:
                failed.append(str(day))
                self.stdout.write(f"{day}: FAILED — {pull.error}")
            else:
                self.stdout.write(
                    f"{day}: OK, {pull.orders} orders, {pull.lines} lines")
            if day == target:
                target_pull = pull
        if send_email and target_pull.status == SalesPull.Status.OK:
            try:
                send_reports(target, target_pull)
            except Exception as exc:
                logger.exception("Report email failed for %s", target)
                target_pull.error = f"Email failed: {exc}"
                target_pull.save(update_fields=["error"])
                self.stdout.write(f"ERROR: email failed: {exc}")
                failed.append(f"{target} (email)")
        if failed:
            raise CommandError("Failed: " + ", ".join(failed))
