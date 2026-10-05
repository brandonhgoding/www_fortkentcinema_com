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
    # Created FAILED so a pull killed mid-run still raises the dashboard alert.
    pull = SalesPull.objects.create(business_date=day,
                                    status=SalesPull.Status.FAILED,
                                    error="Pull did not finish")
    try:
        orders = _closed_orders(gateway.search_orders(*day_bounds(day)))
        lines = [(o, ln) for o in orders for ln in o.lines]
        variations = _resolve_variations(ln.catalog_object_id for _, ln in lines)
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
                stored = _store_line(o, ln, variations, categories,
                                     existing.get((o.order_id, ln.uid)))
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
                categories: dict[str, str], existing: SaleLine | None) -> SaleLine:
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
            "business_date": business_date(o.closed_at),
            "closed_at": o.closed_at,
            "item_name": ln.name,
            "variation_name": ln.variation_name,
            "catalog_object_id": ln.catalog_object_id,
            "quantity": ln.quantity,
            "gross_cents": ln.gross_cents,
            **attribution,
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
