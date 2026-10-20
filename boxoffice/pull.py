"""Pull a business day's Square sales into the SaleLine ledger."""
import datetime
import logging
from collections.abc import Iterable
from typing import Protocol

from boxoffice.gateway import Gateway, GatewayError, OrderData, OrderLine
from boxoffice.models import SaleLine, SalesPull, SquareVariation
from boxoffice.spec import ONLINE_REFERENCE_PREFIX
from cinema.dates import CINEMA_TZ, business_date
from cinema.models import Engagement, Showtime
from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


class WebsiteOrders(Protocol):
    """What the website knows about its own Square orders.

    The tickets app registers an implementation at startup; the ledger never
    imports it. Which showtime an order was for comes from the order itself
    (Square carries our metadata back), so only what Square cannot say is
    asked here.
    """

    def refunded(self, order_ids: Iterable[str]) -> set[str]:
        """The Square ids among ``order_ids`` refunded in full."""

    def paid(self, start: datetime.datetime,
             end: datetime.datetime) -> set[str]:
        """Square ids of orders the buyer paid in [start, end)."""


website: WebsiteOrders | None = None


def register_website(source: WebsiteOrders) -> None:
    global website
    website = source


def day_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """[midnight, next midnight) Eastern, aware."""
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=CINEMA_TZ)
    end = datetime.datetime.combine(
        day + datetime.timedelta(days=1), datetime.time.min, tzinfo=CINEMA_TZ)
    return start, end


__all__ = ["business_date", "CINEMA_TZ"]  # re-exported for the ledger's callers


def sold_at(order: OrderData) -> datetime.datetime | None:
    """When the sale happened: the payment, else the register closing the order.

    A register order is paid and closed in the same moment. A website order
    is paid when the buyer checks out and stays OPEN in Square, so only its
    payment time dates it, including once staff close it days later.
    """
    return order.paid_at or order.closed_at


def day_orders(day: datetime.date, gateway: Gateway) -> list[OrderData]:
    """Every order sold on ``day``: the register's closed orders and the
    website's paid payment-link orders, which Square leaves OPEN."""
    start, end = day_bounds(day)
    orders = _datable_orders(gateway.search_orders(start, end))
    orders += _paid_online_orders(gateway.search_open_orders(start, end))
    return orders


def pull_day(day: datetime.date, gateway: Gateway) -> SalesPull:
    """Store every order line sold on ``day``; the returned row says how it went."""
    # Created FAILED so a pull killed mid-run still raises the dashboard alert.
    pull = SalesPull.objects.create(business_date=day,
                                    status=SalesPull.Status.FAILED,
                                    error="Pull did not finish")
    try:
        orders = day_orders(day, gateway)
        lines = [(o, ln) for o in orders for ln in o.lines]
        variations = _resolve_variations(ln.catalog_object_id for _, ln in lines)
        refunded = _resolve_refunded(o.order_id for o in orders)
        showtimes = _resolve_showtimes(o.showtime_id for o in orders)
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
                stored = _store_line(o, ln, variations, categories, refunded,
                                     showtimes, existing.get((o.order_id, ln.uid)))
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
    """Set each engagement's admissions to its all-time tickets kept."""
    for engagement_id in engagement_ids:
        total = SaleLine.objects.filter(engagement_id=engagement_id).aggregate(
            total=Sum(F("quantity") - F("refunded_quantity")))["total"] or 0
        Engagement.objects.filter(pk=engagement_id).update(admissions=total)


def mark_refunded(order_id: str) -> None:
    """Give back every line of a website order refunded in full, right away.

    The nightly pull derives the same mark from the order's status, but the
    sale day may be past its lookback by the time the refund happens.
    """
    lines = SaleLine.objects.filter(order_id=order_id)
    engagements = {e for e in lines.values_list("engagement_id", flat=True)
                   if e is not None}
    lines.update(refunded_quantity=F("quantity"), refunded_cents=F("gross_cents"))
    recompute_admissions(engagements)


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


def _resolve_showtimes(ids: Iterable[int | None]) -> dict[int, datetime.datetime]:
    """Map showtime pk -> starts_at for the showtimes that still exist.

    The id rides on the order's metadata, written at checkout; the showtime
    may have been deleted since, and a line must never point at a row that
    is gone.
    """
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return dict(Showtime.objects.filter(pk__in=wanted).values_list("pk", "starts_at"))


def recompute_show_dates(showtime_pk: int) -> None:
    """Re-date a moved showtime's lines; the lookback re-pulls only recent ones."""
    starts_at = Showtime.objects.filter(pk=showtime_pk).values_list(
        "starts_at", flat=True).first()
    if starts_at is not None:
        SaleLine.objects.filter(showtime_id=showtime_pk).update(
            show_date=business_date(starts_at))


def _resolve_refunded(order_ids: Iterable[str]) -> set[str]:
    """The Square ids among ``order_ids`` the website refunded in full."""
    if website is None:
        return set()
    return website.refunded(set(order_ids))


def _resolve_categories(gateway: Gateway,
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
    if website is None:
        return []
    paid = website.paid(*day_bounds(day))
    stored = set(SaleLine.objects.filter(order_id__in=paid)
                 .values_list("order_id", flat=True))
    missing = sorted(paid - stored)
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
                categories: dict[str, str], refunded: set[str],
                showtimes: dict[int, datetime.datetime],
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
    given_back = o.order_id in refunded
    sold = sold_at(o)
    assert sold is not None  # day_orders keeps only orders with a sale time
    starts_at = showtimes.get(o.showtime_id) if o.showtime_id is not None else None
    stored, _ = SaleLine.objects.update_or_create(
        order_id=o.order_id, line_uid=ln.uid,
        defaults={
            "business_date": business_date(sold),
            "show_date": business_date(starts_at if starts_at else sold),
            "closed_at": o.closed_at,
            # Square allows longer names than these columns; Postgres would
            # refuse the row and with it the whole day, so cut them to fit.
            "item_name": ln.name[:200],
            "variation_name": ln.variation_name[:80],
            "catalog_object_id": ln.catalog_object_id,
            "quantity": ln.quantity,
            "gross_cents": ln.gross_cents,
            "showtime_id": o.showtime_id if starts_at else None,
            "refunded_quantity": ln.quantity if given_back else 0,
            "refunded_cents": ln.gross_cents if given_back else 0,
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
