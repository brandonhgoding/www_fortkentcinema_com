"""Keep one Square ticket item per confirmed engagement in step with Django."""
import datetime
import logging

from boxoffice.gateway import (
    GatewayError,
    SquareGateway,
    UpsertResult,
    VersionMismatch,
    get_gateway,
)
from boxoffice.models import SquareItem, SquareVariation
from boxoffice.spec import ItemSpec, desired_item
from cinema.models import Engagement, EngagementStatus
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def live_item(engagement: Engagement) -> SquareItem | None:
    return SquareItem.objects.filter(
        engagement=engagement, deleted_at__isnull=True).first()


def should_have_item(engagement: Engagement, today: datetime.date) -> bool:
    return (engagement.status == EngagementStatus.CONFIRMED
            and engagement.end_date >= today)


def _resolve(gateway: SquareGateway | None) -> SquareGateway | None:
    gateway = gateway if gateway is not None else get_gateway()
    if gateway is None:
        logger.info("Square sync disabled (no SQUARE_ACCESS_TOKEN)")
    return gateway


def _unchanged(item: SquareItem | None, spec: ItemSpec) -> bool:
    if item is None or item.square_id is None or item.last_error:
        return False
    if item.name != spec.name:
        return False
    stored = sorted(item.variations.values_list(
        "tier", "name", "sku", "price_cents", "ordinal"))
    wanted = sorted((v.tier, v.name, v.sku, v.price_cents, v.ordinal)
                    for v in spec.variations)
    return stored == wanted


def _record_error(engagement: Engagement, message: str) -> SquareItem:
    logger.warning("Square push failed for engagement %s: %s",
                   engagement.pk, message)
    item, _ = SquareItem.objects.get_or_create(
        engagement=engagement, deleted_at__isnull=True,
        defaults={"name": engagement.display_title})
    item.last_error = message
    item.save(update_fields=["last_error"])
    return item


@transaction.atomic
def _write_back(engagement: Engagement, item: SquareItem | None, spec: ItemSpec,
                result: UpsertResult) -> SquareItem:
    if item is None:
        item = SquareItem(engagement=engagement)
    item.square_id = result.item_id
    item.version = result.version
    item.name = spec.name
    item.synced_at = timezone.now()
    item.last_error = ""
    item.save()
    # Update in place rather than recreate, so sale lines keep their links.
    for v in spec.variations:
        SquareVariation.objects.update_or_create(
            item=item, tier=v.tier,
            defaults={"square_id": result.variation_ids_by_tier[v.tier],
                      "sku": v.sku, "name": v.name,
                      "price_cents": v.price_cents, "ordinal": v.ordinal})
    item.variations.exclude(tier__in=[v.tier for v in spec.variations]).delete()
    return item


def _upsert(gateway: SquareGateway, item: SquareItem | None,
            spec: ItemSpec) -> UpsertResult:
    if item is None or item.square_id is None:
        return gateway.upsert_item(spec, item_id=None, version=None,
                                   variation_ids_by_tier={})
    try:
        return gateway.upsert_item(
            spec, item_id=item.square_id, version=item.version,
            variation_ids_by_tier=dict(
                item.variations.values_list("tier", "square_id")))
    except VersionMismatch:
        remote = gateway.retrieve_item(item.square_id)
        logger.warning(
            "Square item %s was edited outside Django (version %s, name %r); "
            "overwriting the external edit", remote.item_id, remote.version,
            remote.name)
        ids = {v.tier: remote.variation_ids_by_sku[v.sku]
               for v in spec.variations if v.sku in remote.variation_ids_by_sku}
        return gateway.upsert_item(spec, item_id=remote.item_id,
                                   version=remote.version,
                                   variation_ids_by_tier=ids)


def push(engagement: Engagement,
         gateway: SquareGateway | None = None) -> SquareItem | None:
    gateway = _resolve(gateway)
    if gateway is None:
        return None
    try:
        spec = desired_item(engagement)
    except ValueError as exc:
        return _record_error(engagement, str(exc))
    item = live_item(engagement)
    if _unchanged(item, spec):
        return item
    try:
        result = _upsert(gateway, item, spec)
    except GatewayError as exc:
        return _record_error(engagement, str(exc))
    return _write_back(engagement, item, spec, result)


def _retire(item: SquareItem) -> None:
    # The row and its variations stay so old sales still resolve.
    item.deleted_at = timezone.now()
    item.save(update_fields=["deleted_at"])


def delete(engagement: Engagement, gateway: SquareGateway | None = None) -> None:
    item = live_item(engagement)
    if item is None:
        return
    gateway = _resolve(gateway)
    if item.square_id is not None and gateway is not None:
        gateway.delete_item(item.square_id)
    _retire(item)


def sync(engagement: Engagement, gateway: SquareGateway | None = None) -> None:
    gateway = gateway if gateway is not None else get_gateway()
    try:
        if should_have_item(engagement, timezone.localdate()):
            push(engagement, gateway)
        else:
            delete(engagement, gateway)
    except (GatewayError, ValueError) as exc:
        logger.warning("Square sync failed for engagement %s: %s",
                       engagement.pk, exc)


def schedule(engagement: Engagement) -> None:
    transaction.on_commit(lambda: sync(engagement))
