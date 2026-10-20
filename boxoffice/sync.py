"""Keep one Square ticket item per confirmed engagement in step with Django."""
import dataclasses
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
from boxoffice.posters import fetch_poster
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
    # Cut to the column: the error may be that the title is too long for it.
    item, _ = SquareItem.objects.get_or_create(
        engagement=engagement, deleted_at__isnull=True,
        defaults={"name": engagement.title[:200]})
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


def _delete_remote(gateway: SquareGateway, item: SquareItem) -> None:
    """Remove the item from Square, then its poster image as best effort.

    Square keeps images as separate catalog objects, so deleting the item
    alone would leave an orphan picture behind for every finished run. A
    failure to remove the picture is logged, not raised: the item is gone,
    which is what matters for the register.
    """
    if item.square_id is not None:
        gateway.delete_item(item.square_id)
    if item.image_id:
        try:
            gateway.delete_item(item.image_id)
        except GatewayError as exc:
            logger.warning("Could not delete image %s for item %s: %s",
                           item.image_id, item.square_id, exc)


def delete(engagement: Engagement, gateway: SquareGateway | None = None) -> None:
    item = live_item(engagement)
    if item is None:
        return
    gateway = _resolve(gateway)
    if gateway is not None:
        _delete_remote(gateway, item)
    _retire(item)


def sync(engagement: Engagement, gateway: SquareGateway | None = None) -> None:
    """Never raises: it runs after commit, where an error would fail the save."""
    try:
        gateway = gateway if gateway is not None else get_gateway()
        if should_have_item(engagement, timezone.localdate()):
            push(engagement, gateway)
        else:
            delete(engagement, gateway)
    except (GatewayError, ValueError) as exc:
        logger.warning("Square sync failed for engagement %s: %s",
                       engagement.pk, exc)
    except Exception:
        logger.exception("Unexpected error syncing engagement %s to Square",
                         engagement.pk)


def _sync_by_pk(pk: int) -> None:
    engagement = Engagement.objects.filter(pk=pk).first()
    if engagement is not None:
        sync(engagement)


def schedule(engagement: Engagement) -> None:
    pk = engagement.pk
    transaction.on_commit(lambda: _sync_by_pk(pk))


@dataclasses.dataclass
class ReconcileReport:
    """What a reconcile did (or, with dry_run, would do).

    ``pushed``, ``deleted`` and ``images`` hold engagement pks. A live row whose
    engagement was deleted from Django is still removed from Square and
    retired, but has no engagement pk to list, so it is not counted in
    ``deleted``.
    """
    pushed: list[int] = dataclasses.field(default_factory=list)
    deleted: list[int] = dataclasses.field(default_factory=list)
    unknown_items: list[str] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)
    # Poster icons: ``images`` holds engagement pks whose item got one; a
    # poster that could not be fetched or uploaded is a skip, not an error.
    images: list[int] = dataclasses.field(default_factory=list)
    image_skips: list[str] = dataclasses.field(default_factory=list)


def _audit_remote(today: datetime.date, gateway: SquareGateway, dry_run: bool,
                  report: ReconcileReport) -> None:
    try:
        remote_items = gateway.list_ticket_items()
    except GatewayError as exc:
        report.errors.append(f"Could not list Square ticket items: {exc}")
        return
    known = set(SquareItem.objects.filter(
        deleted_at__isnull=True, square_id__isnull=False
    ).values_list("square_id", flat=True))
    for remote in remote_items:
        if remote.item_id in known:
            continue
        if any(sku and sku.startswith("fkc-eng-")
               for sku in remote.variation_ids_by_sku):
            report.errors.append(
                f"Django-made item without a link row: {remote.item_id}")
        else:
            report.unknown_items.append(f"{remote.name} ({remote.item_id})")
    _audit_missing({r.item_id for r in remote_items}, today, gateway, dry_run,
                   report)


def _audit_missing(listed: set[str], today: datetime.date, gateway: SquareGateway,
                   dry_run: bool, report: ReconcileReport) -> None:
    """Live rows whose item is not in the ticket category: deleted or moved by hand.

    A deleted item's row is retired so the push pass that follows recreates it;
    a moved item is re-pushed, which puts it back in the category.
    """
    missing = SquareItem.objects.filter(
        deleted_at__isnull=True, square_id__isnull=False
    ).exclude(square_id__in=listed).select_related("engagement").order_by("pk")
    for row in missing:
        engagement = row.engagement
        if engagement is None or not should_have_item(engagement, today):
            continue  # The delete pass removes it.
        if dry_run:
            report.errors.append(
                f"Item {row.square_id} for engagement {engagement.pk} is missing "
                "from the ticket category in Square; it would be restored")
            continue
        try:
            try:
                gateway.retrieve_item(row.square_id)
            except GatewayError:
                _retire(row)
                report.errors.append(
                    f"Item {row.square_id} for engagement {engagement.pk} was "
                    "deleted in Square; it will be recreated")
                continue
            spec = desired_item(engagement)
            result = _upsert(gateway, row, spec)
            _write_back(engagement, row, spec, result)
            report.pushed.append(engagement.pk)
        except Exception as exc:
            report.errors.append(
                f"Restoring item {row.square_id} for engagement "
                f"{engagement.pk}: {exc!r}")


def _reconcile_pushes(today: datetime.date, gateway: SquareGateway,
                      dry_run: bool, report: ReconcileReport) -> None:
    wanted = Engagement.objects.filter(
        status=EngagementStatus.CONFIRMED, end_date__gte=today).order_by("pk")
    for engagement in wanted:
        try:
            _reconcile_push(engagement, gateway, dry_run, report)
        except Exception as exc:
            report.errors.append(f"Pushing engagement {engagement.pk}: {exc!r}")


def _reconcile_push(engagement: Engagement, gateway: SquareGateway,
                    dry_run: bool, report: ReconcileReport) -> None:
    try:
        spec = desired_item(engagement)
    except ValueError as exc:
        if not dry_run:
            _record_error(engagement, str(exc))
        report.errors.append(f"Engagement {engagement.pk}: {exc}")
        return
    if _unchanged(live_item(engagement), spec):
        return
    if dry_run:
        report.pushed.append(engagement.pk)
        return
    item = push(engagement, gateway)
    if item is not None and item.last_error:
        report.errors.append(f"Engagement {engagement.pk}: {item.last_error}")
    else:
        report.pushed.append(engagement.pk)


def _reconcile_deletes(today: datetime.date, gateway: SquareGateway,
                       dry_run: bool, report: ReconcileReport) -> None:
    live_rows = SquareItem.objects.filter(
        deleted_at__isnull=True).select_related("engagement").order_by("pk")
    for row in live_rows:
        try:
            _reconcile_delete(row, today, gateway, dry_run, report)
        except Exception as exc:
            report.errors.append(
                f"Deleting item row {row.pk} (engagement {row.engagement_id}): "
                f"{exc!r}")


def _reconcile_delete(row: SquareItem, today: datetime.date,
                      gateway: SquareGateway, dry_run: bool,
                      report: ReconcileReport) -> None:
    engagement = row.engagement
    if engagement is None:
        # The engagement was deleted outside the dashboard (e.g. the admin).
        if not dry_run:
            _delete_remote(gateway, row)
            _retire(row)
        return
    if should_have_item(engagement, today):
        return
    if dry_run:
        report.deleted.append(engagement.pk)
        return
    delete(engagement, gateway)
    report.deleted.append(engagement.pk)


def _reconcile_images(gateway: SquareGateway, dry_run: bool,
                      report: ReconcileReport) -> None:
    """Give every live item without a picture its film's poster as the icon.

    Deferred to the nightly run on purpose: the download and upload would
    otherwise sit inside the dashboard save. Posters are decoration, so a
    missing or unreachable one is reported as a skip and tried again the
    next night, never as an error.
    """
    rows = SquareItem.objects.filter(
        deleted_at__isnull=True, square_id__isnull=False, image_id="",
        engagement__isnull=False,
    ).select_related("engagement").order_by("pk")
    for row in rows:
        engagement = row.engagement
        film = engagement.primary_film
        url = film.poster_url if film is not None else ""
        if not url:
            continue
        if dry_run:
            report.images.append(engagement.pk)
            continue
        try:
            image = fetch_poster(url)
            if image is None:
                report.image_skips.append(
                    f"{engagement.title}: poster could not be fetched "
                    f"from {url}")
                continue
            row.image_id = gateway.upload_item_image(
                row.square_id, image, engagement.title)
            row.save(update_fields=["image_id"])
            report.images.append(engagement.pk)
        except Exception as exc:
            report.image_skips.append(f"{engagement.title}: {exc!r}")


def reconcile(today: datetime.date, gateway: SquareGateway | None = None,
              *, dry_run: bool = False) -> ReconcileReport:
    """Bring Square in line with Django; with dry_run, only report the plan."""
    report = ReconcileReport()
    gateway = _resolve(gateway)
    if gateway is None:
        return report
    # Audit first: the listing is a snapshot of what Square held before we
    # write, and rows retired for vanished items are recreated by the pushes.
    _audit_remote(today, gateway, dry_run, report)
    _reconcile_pushes(today, gateway, dry_run, report)
    _reconcile_deletes(today, gateway, dry_run, report)
    # Posters last, so nothing is uploaded to an item the delete pass removed.
    _reconcile_images(gateway, dry_run, report)
    return report
