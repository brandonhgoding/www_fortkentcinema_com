"""Pull a business day's Square sales into the SaleLine ledger."""
import datetime
import logging
from collections.abc import Iterable
from zoneinfo import ZoneInfo

from boxoffice.gateway import GatewayError, OrderData, OrderLine, SquareGateway
from boxoffice.models import SaleLine, SalesPull, SquareVariation
from cinema.models import Engagement
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")


def day_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """[midnight, next midnight) Eastern, aware."""
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=EASTERN)
    end = datetime.datetime.combine(
        day + datetime.timedelta(days=1), datetime.time.min, tzinfo=EASTERN)
    return start, end


def business_date(closed_at: datetime.datetime) -> datetime.date:
    return closed_at.astimezone(EASTERN).date()


def pull_day(day: datetime.date, gateway: SquareGateway) -> SalesPull:
    """Store every order line closed on ``day``; the returned row says how it went."""
    pull = SalesPull.objects.create(business_date=day)
    try:
        orders = _closed_orders(gateway.search_orders(*day_bounds(day)))
        lines = [(o, ln) for o in orders for ln in o.lines]
        variations = _resolve_variations(ln.catalog_object_id for _, ln in lines)
        categories = _resolve_categories(
            gateway,
            {ln.catalog_object_id for _, ln in lines
             if ln.catalog_object_id and ln.catalog_object_id not in variations})
        with transaction.atomic():
            touched = set()
            for o, ln in lines:
                stored = _store_line(o, ln, variations, categories)
                if stored.engagement_id is not None:
                    touched.add(stored.engagement_id)
            recompute_admissions(touched)
    except GatewayError as exc:
        logger.warning("Sales pull for %s failed: %s", day, exc)
        return _finish(pull, SalesPull.Status.FAILED, error=str(exc))
    except Exception as exc:
        logger.exception("Sales pull for %s failed unexpectedly", day)
        return _finish(pull, SalesPull.Status.FAILED, error=repr(exc))
    return _finish(pull, SalesPull.Status.OK, orders=len(orders), lines=len(lines))


def recompute_admissions(engagement_ids: Iterable[int]) -> None:
    """Set each engagement's admissions to its all-time ticket quantity."""
    for engagement_id in engagement_ids:
        total = SaleLine.objects.filter(engagement_id=engagement_id).aggregate(
            total=Sum("quantity"))["total"] or 0
        Engagement.objects.filter(pk=engagement_id).update(admissions=total)


def _closed_orders(orders: list[OrderData]) -> list[OrderData]:
    kept = []
    for o in orders:
        if o.closed_at is None:
            logger.warning("Skipping order %s with no closed_at", o.order_id)
        else:
            kept.append(o)
    return kept


def _resolve_variations(ids: Iterable[str]) -> dict[str, SquareVariation]:
    """Map Square variation ID -> our row, by square_id only (SKUs repeat)."""
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {v.square_id: v for v in
            SquareVariation.objects.filter(square_id__in=wanted).select_related("item")}


def _resolve_categories(gateway: SquareGateway,
                        unknown_ids: set[str]) -> dict[str, str]:
    if not unknown_ids:
        return {}
    return gateway.lookup_categories(sorted(unknown_ids))


def _store_line(o: OrderData, ln: OrderLine, variations: dict[str, SquareVariation],
                categories: dict[str, str]) -> SaleLine:
    variation = variations.get(ln.catalog_object_id) if ln.catalog_object_id else None
    if variation is not None:
        category_id = settings.SQUARE_TICKET_CATEGORY_ID
    else:
        category_id = categories.get(ln.catalog_object_id, "")
    stored, _ = SaleLine.objects.update_or_create(
        order_id=o.order_id, line_uid=ln.uid,
        defaults={
            "business_date": business_date(o.closed_at),
            "closed_at": o.closed_at,
            "item_name": ln.name,
            "variation_name": ln.variation_name,
            "catalog_object_id": ln.catalog_object_id,
            "category_id": category_id,
            "quantity": ln.quantity,
            "gross_cents": ln.gross_cents,
            "variation": variation,
            "engagement_id": variation.item.engagement_id if variation else None,
        },
    )
    return stored


def _finish(pull: SalesPull, status: str, *, orders: int = 0, lines: int = 0,
            error: str = "") -> SalesPull:
    pull.status = status
    pull.orders = orders
    pull.lines = lines
    pull.error = error
    pull.finished_at = timezone.now()
    pull.save()
    return pull
