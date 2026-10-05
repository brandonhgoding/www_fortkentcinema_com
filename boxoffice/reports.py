import datetime
import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string

from .models import EmailReport, SaleLine, SalesPull
from .spec import priced_tiers

logger = logging.getLogger(__name__)

TEMPLATES = {
    EmailReport.Kind.OWNER_SUMMARY: "boxoffice/email/owner_summary.txt",
    EmailReport.Kind.TICKET_REPORT: "boxoffice/email/ticket_report.txt",
}
SENT_FLAGS = {
    EmailReport.Kind.OWNER_SUMMARY: "owner_email_sent",
    EmailReport.Kind.TICKET_REPORT: "report_email_sent",
}


@dataclass(frozen=True)
class ItemTotal:
    name: str
    quantity: int
    gross_cents: int

    @property
    def gross_dollars(self) -> str:
        return f"{self.gross_cents / 100:.2f}"


def _group(lines: QuerySet[SaleLine]) -> list[ItemTotal]:
    rows = lines.values("item_name").annotate(
        quantity=Sum("quantity"), gross=Sum("gross_cents"))
    totals = [ItemTotal(r["item_name"], r["quantity"], r["gross"]) for r in rows]
    return sorted(totals, key=lambda t: (-t.gross_cents, t.name))


def owner_summary(day: datetime.date) -> list[ItemTotal]:
    return _group(SaleLine.objects.filter(business_date=day))


def ticket_report(day: datetime.date) -> list[ItemTotal]:
    wanted = Q(engagement__isnull=False, engagement__in_ticket_report=True)
    category = settings.SQUARE_TICKET_CATEGORY_ID
    if category:
        wanted |= Q(engagement__isnull=True, category_id=category)
    return _group(SaleLine.objects.filter(wanted, business_date=day))


def tier_totals(day: datetime.date) -> dict[str, int]:
    totals = {tier: 0 for tier, _ in priced_tiers()}
    rows = (
        SaleLine.objects.filter(
            business_date=day, engagement__isnull=False, variation__isnull=False)
        .values("variation__tier")
        .annotate(quantity=Sum("quantity"))
    )
    for r in rows:
        if r["variation__tier"] in totals:
            totals[r["variation__tier"]] = r["quantity"]
    return totals


def render_report(kind: str, day: datetime.date, rows: list[ItemTotal]) -> str:
    return render_to_string(TEMPLATES[kind], {
        "day": day,
        "rows": rows,
        "total_quantity": sum(r.quantity for r in rows),
        "total_dollars": f"{sum(r.gross_cents for r in rows) / 100:.2f}",
    })


def send_reports(day: datetime.date, pull: SalesPull, *, dry_run: bool = False) -> None:
    builders = {
        EmailReport.Kind.OWNER_SUMMARY: owner_summary,
        EmailReport.Kind.TICKET_REPORT: ticket_report,
    }
    for kind, build in builders.items():
        report = EmailReport.objects.filter(kind=kind).first()
        if report is None or not report.enabled:
            logger.info("Skipping %s email for %s: not enabled", kind, day)
            continue
        to = report.to_addresses()
        if not to:
            logger.info("Skipping %s email for %s: no To recipients", kind, day)
            continue
        body = render_report(kind, day, build(day))
        cc = report.cc_addresses()
        if dry_run:
            logger.info("Dry run %s email\nSubject: %s\nTo: %s\nCc: %s\n\n%s",
                        kind, report.subject, ", ".join(to), ", ".join(cc), body)
            continue
        EmailMessage(subject=report.subject, body=body, to=to, cc=cc).send()
        flag = SENT_FLAGS[kind]
        setattr(pull, flag, True)
        pull.save(update_fields=[flag])
        logger.info("Sent %s email for %s to %s", kind, day, ", ".join(to))


@dataclass(frozen=True)
class DaySales:
    gross_cents: int
    tickets: int
    concessions_cents: int

    @property
    def gross_dollars(self) -> str:
        return f"{self.gross_cents / 100:.2f}"

    @property
    def concessions_dollars(self) -> str:
        return f"{self.concessions_cents / 100:.2f}"


def day_sales(day: datetime.date) -> DaySales:
    tickets = Q(engagement__isnull=False)
    totals = SaleLine.objects.filter(business_date=day).aggregate(
        gross=Coalesce(Sum("gross_cents"), 0),
        tickets=Coalesce(Sum("quantity", filter=tickets), 0),
        concessions=Coalesce(Sum("gross_cents", filter=~tickets), 0),
    )
    return DaySales(totals["gross"], totals["tickets"], totals["concessions"])


def sales_panel(today: datetime.date) -> dict | None:
    if not settings.SQUARE_ACCESS_TOKEN:
        return None
    last_week = today - datetime.timedelta(days=8)
    return {
        "yesterday": day_sales(today - datetime.timedelta(days=1)),
        "last_week": day_sales(last_week),
        "yesterday_label": "Yesterday",
        "last_week_label": f"Last {last_week:%A}",
        "has_pulls": SalesPull.objects.exists(),
    }


def pull_status(day: datetime.date) -> str:
    latest = SalesPull.objects.filter(business_date=day).order_by("-started_at").first()
    return latest.status if latest else "MISSING"
