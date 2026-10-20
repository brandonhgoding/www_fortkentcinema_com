"""Pull a business day's Square sales into the SaleLine ledger."""
import datetime
import logging
from collections.abc import Iterable
from zoneinfo import ZoneInfo

from boxoffice.gateway import GatewayError, OrderData, OrderLine, SquareGateway
from boxoffice.models import SaleLine, SalesPull, SquareVariation
from boxoffice.spec import ONLINE_REFERENCE_PREFIX
from cinema.models import Engagement
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from tickets.models import TicketOrder

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")


def day_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """[midnight, next midnight) Eastern, aware."""
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=EASTERN)
    end = datetime.datetime.combine(
        day + datetime.timedelta(days=1), datetime.time.min, tzinfo=EASTERN)
    return start, end


def business_date(when: datetime.datetime) -> datetime.date:
    """The Eastern calendar day a sale (or anything else) happened on."""
    return when.astimezone(EASTERN).date()


def sold_at(order: OrderData) -> datetime.datetime | None:
    """When the sale happened: the payment, else the register closing the order.

    A register order is paid and closed in the same moment. A website order
    is paid when the buyer checks out and stays OPEN in Square, so only its
    payment time dates it, including once staff close it days later.
    """
    return order.paid_at or order.closed_at


def day_orders(day: datetime.date, gateway: SquareGateway) -> list[OrderData]:
    """Every order sold on ``day``: the register's closed orders and the
    website's paid payment-link orders, which Square leaves OPEN."""
    start, end = day_bounds(day)
    orders = _datable_orders(gateway.search_orders(start, end))
    orders += _paid_online_orders(gateway.search_open_orders(start, end))
    return orders


def pull_day(day: datetime.date, gateway: SquareGateway) -> SalesPull:
    """Store every order line sold on ``day``; the returned row says how it went."""
    # Created FAILED so a pull killed mid-run still raises the dashboard alert.
    pull = SalesPull.objects.create(business_date=day,
                                    status=SalesPull.Status.FAILED,
                                    error="Pull did not finish")
    try:
        orders = day_orders(day, gateway)
        lines = [(o, ln) for o in orders for ln in o.lines]
        variations = _resolve_variations(ln.catalog_object_id for _, ln in lines)
        showtimes = _resolve_showtimes(o.order_id for o in orders)
        categories = _resolve_categories(
            gateway,
            {ln.catalog_object_id for _, ln in lines
             if ln.catalog_object_id and ln.catalog_object_id not in variations})
        with transaction.atomic():
            existing = _existing_rows(lines)
            # Engagements losing lines must be recomputed too.
            touched = {row.engagement_id for row in existing.values()
                       if row.engagement_id is not None}
            for o, ln in lines:
                stored = _store_line(o, ln, variations, categories, showtimes,
                                     existing.get((o.order_id, ln.uid)))
                if stored.engagement_id is not None:
                    touched.add(stored.engagement_id)
            recompute_admissions(touched)
        missing = _missing_online_orders(day)
    except GatewayError as exc:
        logger.warning("Sales pull for %s failed: %s", day, exc)
        return _finish(pull, SalesPull.Status.FAILED, error=str(exc))
    except Exception as exc:
        logger.exception("Sales pull for %s failed unexpectedly", day)
        return _finish(pull, SalesPull.Status.FAILED, error=repr(exc))
    return _finish(pull, SalesPull.Status.OK, orders=len(orders), lines=len(lines),
                   missing_online=len(missing))


def recompute_admissions(engagement_ids: Iterable[int]) -> None:
    """Set each engagement's admissions to its all-time ticket quantity."""
    for engagement_id in engagement_ids:
        total = SaleLine.objects.filter(engagement_id=engagement_id).aggregate(
            total=Sum("quantity"))["total"] or 0
        Engagement.objects.filter(pk=engagement_id).update(admissions=total)


def _datable_orders(orders: list[OrderData]) -> list[OrderData]:
    kept = []
    for o in orders:
        if sold_at(o) is None:
            logger.warning("Skipping order %s with no closed_at or payment",
                           o.order_id)
        else:
            kept.append(o)
    return kept


def _paid_online_orders(orders: list[OrderData]) -> list[OrderData]:
    """The website's orders that have been paid.

    The open search also returns links nobody paid and the register's open
    tabs; a part-paid tab is not a sale yet.
    """
    return [o for o in orders
            if o.reference_id.startswith(ONLINE_REFERENCE_PREFIX)
            and o.tenders and o.paid_at is not None]


def _resolve_variations(ids: Iterable[str]) -> dict[str, SquareVariation]:
    """Map Square variation ID -> our row, by square_id only (SKUs repeat)."""
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {v.square_id: v for v in
            SquareVariation.objects.filter(square_id__in=wanted).select_related("item")}


def _resolve_showtimes(order_ids: Iterable[str]) -> dict[str, int]:
    """Map Square order ID -> showtime pk for orders placed through the website."""
    return dict(
        TicketOrder.objects.filter(square_order_id__in=set(order_ids))
        .values_list("square_order_id", "showtime_id"))


def _resolve_categories(gateway: SquareGateway,
                        unknown_ids: set[str]) -> dict[str, str]:
    if not unknown_ids:
        return {}
    return gateway.lookup_categories(sorted(unknown_ids))


def _missing_online_orders(day: datetime.date) -> list[str]:
    """Square ids of website orders paid on ``day`` with no line in the ledger.

    Square's own records are the ledger's source; this only says when they
    disagree with ours, so a change in what the open-order search returns
    shows up on the dashboard instead of as quietly short reports.
    """
    start, end = day_bounds(day)
    paid = (TicketOrder.objects.filter(paid_at__gte=start, paid_at__lt=end)
            .exclude(square_order_id="")
            .values_list("square_order_id", flat=True))
    stored = set(SaleLine.objects.filter(order_id__in=paid)
                 .values_list("order_id", flat=True))
    missing = sorted(set(paid) - stored)
    if missing:
        logger.warning("Paid online orders missing from the ledger for %s: %s",
                       day, ", ".join(missing))
    return missing


def _existing_rows(lines: list[tuple[OrderData, OrderLine]]
                   ) -> dict[tuple[str, str], SaleLine]:
    """The ledger rows this pull will overwrite, keyed by (order_id, line_uid)."""
    keys = {(o.order_id, ln.uid) for o, ln in lines}
    if not keys:
        return {}
    rows = SaleLine.objects.filter(order_id__in={k[0] for k in keys}).only(
        "order_id", "line_uid", "variation_id", "engagement_id", "category_id")
    return {(r.order_id, r.line_uid): r for r in rows
            if (r.order_id, r.line_uid) in keys}


def _store_line(o: OrderData, ln: OrderLine, variations: dict[str, SquareVariation],
                categories: dict[str, str], showtimes: dict[str, int],
                existing: SaleLine | None) -> SaleLine:
    variation = variations.get(ln.catalog_object_id) if ln.catalog_object_id else None
    if variation is not None:
        attribution = {
            "variation_id": variation.pk,
            "engagement_id": variation.item.engagement_id,
            "category_id": settings.SQUARE_TICKET_CATEGORY_ID,
        }
    else:
        # The catalog no longer resolves this line: keep what an earlier pull
        # attributed rather than stripping it.
        attribution = {
            "variation_id": existing.variation_id if existing else None,
            "engagement_id": existing.engagement_id if existing else None,
            "category_id": (categories.get(ln.catalog_object_id, "")
                            or (existing.category_id if existing else "")),
        }
    stored, _ = SaleLine.objects.update_or_create(
        order_id=o.order_id, line_uid=ln.uid,
        defaults={
            # day_orders keeps only orders with a sale time.
            "business_date": business_date(sold_at(o)),  # type: ignore[arg-type]
            "closed_at": o.closed_at,
            # Square allows longer names than these columns; Postgres would
            # refuse the row and with it the whole day, so cut them to fit.
            "item_name": ln.name[:200],
            "variation_name": ln.variation_name[:80],
            "catalog_object_id": ln.catalog_object_id,
            "quantity": ln.quantity,
            "gross_cents": ln.gross_cents,
            "showtime_id": showtimes.get(o.order_id),
            **attribution,
        },
    )
    return stored


def _finish(pull: SalesPull, status: str, *, orders: int = 0, lines: int = 0,
            missing_online: int = 0, error: str = "") -> SalesPull:
    pull.status = status
    pull.orders = orders
    pull.lines = lines
    pull.missing_online = missing_online
    pull.error = error
    pull.finished_at = timezone.now()
    pull.save()
    return pull
