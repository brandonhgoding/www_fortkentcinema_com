"""The only module that talks to Square. Everything else uses these types."""
import datetime
import decimal
import functools
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Protocol, TypeVar

import httpx
import pydantic
from boxoffice.spec import ItemSpec, VariationSpec
from django.conf import settings
from square import Square
from square.core.api_error import ApiError
from square.environment import SquareEnvironment

T = TypeVar("T")
logger = logging.getLogger(__name__)


class GatewayError(Exception):
    pass


class VersionMismatch(GatewayError):
    pass


class NotFound(GatewayError):
    """Square has no such object: the one failure a retry cannot fix."""


@dataclass(frozen=True)
class RemoteItem:
    item_id: str
    version: int
    name: str
    variation_ids_by_sku: dict[str, str]


@dataclass(frozen=True)
class UpsertResult:
    item_id: str
    version: int
    variation_ids_by_tier: dict[str, str]


@dataclass(frozen=True)
class OrderLine:
    uid: str
    name: str
    variation_name: str
    catalog_object_id: str  # "" when absent
    quantity: int
    gross_cents: int  # total_money.amount


@dataclass(frozen=True)
class OrderData:
    order_id: str
    closed_at: datetime.datetime | None  # aware; None when Square omits it
    lines: tuple[OrderLine, ...]
    # When the buyer paid: the first tender's created_at, else the order's
    # created_at; aware, None when Square gives neither.
    paid_at: datetime.datetime | None = None
    showtime_id: int | None = None  # from metadata.showtime, which we write


def _call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run ``fn``, which calls Square and reads the reply, as one gateway step.

    Every way that can go wrong is a GatewayError, so callers have one thing
    to catch: the pull marks the day FAILED, the sync records the error.
    The reply is read inside too, because a shape this module does not
    expect must not escape as a bare AttributeError and turn into a 500.
    """
    try:
        return fn(*args, **kwargs)
    except ApiError as exc:
        codes = {getattr(e, "code", None) for e in exc.errors}
        if "VERSION_MISMATCH" in codes:
            raise VersionMismatch(str(exc.body)) from exc
        if "NOT_FOUND" in codes or exc.status_code == 404:
            raise NotFound(str(exc.body)) from exc
        raise GatewayError(str(exc.body)) from exc
    except (httpx.HTTPError, pydantic.ValidationError) as exc:
        # The SDK does not wrap transport failures or unparseable responses.
        raise GatewayError(f"{type(exc).__name__}: {exc}") from exc
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise GatewayError(
            f"Unexpected response: {type(exc).__name__}: {exc}") from exc


def _temp_item_id(spec: ItemSpec) -> str:
    return f"#eng-{spec.engagement_id}"


def _temp_variation_id(spec: ItemSpec, tier: str) -> str:
    return f"#eng-{spec.engagement_id}-{tier}"


def _category_ids(obj: Any) -> list[str]:
    # batch_get's related_objects carry every type (images, categories, taxes);
    # only ITEM objects have item_data, and pydantic raises on the rest.
    item_data = getattr(obj, "item_data", None)
    if item_data is None:
        return []
    return [c.id for c in (item_data.categories or [])]


def _remote_item(obj: Any) -> RemoteItem:
    return RemoteItem(
        item_id=obj.id,
        version=obj.version,
        name=obj.item_data.name,
        # Hand-made variations often have no SKU; they cannot be matched by SKU.
        variation_ids_by_sku={
            v.item_variation_data.sku: v.id for v in (obj.item_data.variations or [])
            if v.item_variation_data.sku
        },
    )


def _order_line(line: Any) -> OrderLine:
    return OrderLine(
        uid=line.uid,
        # Register "custom amount" charges (item_type CUSTOM_AMOUNT) have no
        # name; the ledger column is not nullable.
        name=line.name or "Custom amount",
        variation_name=line.variation_name or "",
        catalog_object_id=line.catalog_object_id or "",
        quantity=_whole_units(line.quantity),
        gross_cents=line.total_money.amount,
    )


def _whole_units(quantity: str) -> int:
    """Square's decimal quantity ("2.00000000") as a count.

    A weighed line ("1.5" lb) counts as its nearest whole unit, rounding
    halves up; the gross is exact either way.
    """
    return int(decimal.Decimal(quantity).to_integral_value(decimal.ROUND_HALF_UP))


def parse_timestamp(value: str | None) -> datetime.datetime | None:
    """Square's RFC 3339 timestamps ("...Z") as aware datetimes; None stays None.

    fromisoformat accepts the trailing Z from Python 3.11 (see the README).
    """
    return datetime.datetime.fromisoformat(value) if value else None


# catalog.batch_get takes at most this many object ids per call.
BATCH_GET_LIMIT = 1000


def _idempotency_key(kind: str, *parts: object) -> str:
    """A key that repeats for the same request, so a retry after a timeout
    finds Square's first answer instead of making a second object. Square
    refuses a reused key with a different body, which is why the body is in
    the hash. At most 128 characters, Square's limit."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part if isinstance(part, bytes)
                      else json.dumps(part, sort_keys=True, default=str).encode())
    return f"{kind}-{digest.hexdigest()}"


def _paid_at(order: Any) -> datetime.datetime | None:
    tenders = order.tenders or []
    first_tender = tenders[0].created_at if tenders else None
    return parse_timestamp(first_tender or order.created_at)


def _order_data(order: Any) -> OrderData:
    return OrderData(
        order_id=order.id,
        closed_at=parse_timestamp(order.closed_at),
        lines=tuple(_order_line(li) for li in (order.line_items or [])),
        paid_at=_paid_at(order),
        showtime_id=_showtime_id(order.metadata),
    )


def _showtime_id(metadata: dict[str, str] | None) -> int | None:
    value = (metadata or {}).get("showtime", "")
    return int(value) if value.isdigit() else None


class Gateway(Protocol):
    """What the rest of the site asks of Square. SquareGateway is the real
    one; boxoffice.tests.fakes.FakeGateway stands in for it in tests, and a
    test pins both to these signatures."""

    def upsert_item(self, spec: ItemSpec, *, item_id: str | None, version: int | None,
                    variation_ids_by_tier: dict[str, str],
                    image_id: str = "") -> UpsertResult: ...

    def delete_item(self, item_id: str) -> None: ...

    def retrieve_item(self, item_id: str) -> RemoteItem: ...

    def search_orders(self, start: datetime.datetime,
                      end: datetime.datetime) -> list[OrderData]: ...

    def list_ticket_items(self) -> list[RemoteItem]: ...

    def upload_item_image(self, item_id: str, image: bytes, name: str) -> str: ...

    def lookup_categories(self, variation_ids: list[str]) -> dict[str, str]: ...


class SquareGateway:
    def __init__(self, client, location_id: str, category_id: str) -> None:
        self.client = client
        self.location_id = location_id
        self.category_id = category_id

    def upsert_item(self, spec: ItemSpec, *, item_id: str | None, version: int | None,
                    variation_ids_by_tier: dict[str, str],
                    image_id: str = "") -> UpsertResult:
        """Create or replace the item; ``image_id`` is the poster to keep on it.

        Catalog updates replace the whole object, so an update that leaves
        out the image loses the poster from the register tile.
        """
        item_obj = self._item_object(spec, item_id, version, variation_ids_by_tier,
                                     image_id)

        def upsert() -> UpsertResult:
            response = self.client.catalog.batch_upsert(
                idempotency_key=_idempotency_key("item", item_obj),
                batches=[{"objects": [item_obj]}])
            minted = {m.client_object_id: m.object_id
                      for m in (response.id_mappings or [])}
            ids_by_tier = {
                v.tier: variation_ids_by_tier.get(v.tier)
                or minted[_temp_variation_id(spec, v.tier)]
                for v in spec.variations
            }
            return UpsertResult(
                item_id=item_id or minted[_temp_item_id(spec)],
                version=response.objects[0].version,
                variation_ids_by_tier=ids_by_tier,
            )

        return _call(upsert)

    def delete_item(self, item_id: str) -> None:
        # batch_delete "succeeds even if only a portion of the targeted IDs can be
        # deleted" (SDK docstring), so an already-gone item does not raise.
        _call(self.client.catalog.batch_delete, object_ids=[item_id])

    def retrieve_item(self, item_id: str) -> RemoteItem:
        # The variations are embedded in the item, so no related objects.
        return _call(lambda: _remote_item(
            self.client.catalog.object.get(item_id).object))

    def search_orders(self, start: datetime.datetime,
                      end: datetime.datetime) -> list[OrderData]:
        """Orders closed in [start, end): the register's completed sales."""
        return self._search("COMPLETED", "closed_at", start, end)

    def _search(self, state: str, stamp: str, start: datetime.datetime,
                end: datetime.datetime) -> list[OrderData]:
        # Square requires the sort field to match the date filter's field.
        query = {
            "filter": {
                "state_filter": {"states": [state]},
                "date_time_filter": {stamp: {
                    "start_at": start.isoformat(), "end_at": end.isoformat()}},
            },
            "sort": {"sort_field": stamp.upper(), "sort_order": "ASC"},
        }
        orders: list[OrderData] = []
        cursor: str | None = None
        while True:
            page = {"cursor": cursor} if cursor else {}
            response = _call(self.client.orders.search,
                             location_ids=[self.location_id], query=query, **page)
            orders.extend(_call(
                lambda: [_order_data(o) for o in (response.orders or [])]))
            cursor = _call(lambda: response.cursor)
            if not cursor:
                return orders

    def list_ticket_items(self) -> list[RemoteItem]:
        return _call(lambda: [
            _remote_item(obj) for obj in self.client.catalog.list(types="ITEM")
            if self.category_id in _category_ids(obj)])

    def upload_item_image(self, item_id: str, image: bytes, name: str) -> str:
        """Attach ``image`` to the item as its primary picture; returns the image id.

        Square cannot fetch from a URL, so the caller downloads the poster and
        hands over the bytes. TMDB posters are JPEGs.
        """
        return _call(lambda: self.client.catalog.images.create(
            request={
                "idempotency_key": _idempotency_key("poster", item_id, image),
                "object_id": item_id,
                "is_primary": True,
                "image": {"type": "IMAGE", "id": "#poster",
                          "image_data": {"name": name}},
            },
            image_file=("poster.jpg", image, "image/jpeg"),
        ).image.id)

    def lookup_categories(self, variation_ids: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        # batch_get takes at most 1000 ids; a day will not need two batches,
        # but a backfill might.
        for start in range(0, len(variation_ids), BATCH_GET_LIMIT):
            result.update(_call(self._lookup_categories,
                                variation_ids[start:start + BATCH_GET_LIMIT]))
        return result

    def _lookup_categories(self, variation_ids: list[str]) -> dict[str, str]:
        # Deleted objects too: a hand-made item removed at cutover still
        # sold today.
        response = self.client.catalog.batch_get(
            object_ids=variation_ids, include_related_objects=True,
            include_deleted_objects=True)
        item_category = {}
        for item in response.related_objects or []:
            cats = _category_ids(item)
            if cats:
                item_category[item.id] = cats[0]
        result = {}
        for var in response.objects or []:
            data = getattr(var, "item_variation_data", None)
            if data is None:
                continue  # a line's catalog_object_id that is not a variation
            cat = item_category.get(data.item_id)
            if cat:
                result[var.id] = cat
        return result

    def _item_object(self, spec: ItemSpec, item_id: str | None, version: int | None,
                     variation_ids_by_tier: dict[str, str], image_id: str) -> dict:
        object_id = item_id or _temp_item_id(spec)
        obj: dict[str, Any] = {"type": "ITEM", "id": object_id}
        if version is not None:
            obj["version"] = version
        obj.update({
            "present_at_all_locations": False,
            "present_at_location_ids": [self.location_id],
            "item_data": {
                "name": spec.name,
                "product_type": "REGULAR",
                "is_taxable": False,
                "categories": [{"id": self.category_id}],
                "reporting_category": {"id": self.category_id},
                "variations": [
                    self._variation_object(spec, v, object_id, version,
                                           variation_ids_by_tier.get(v.tier))
                    for v in spec.variations
                ],
            },
        })
        if image_id:
            obj["item_data"]["image_ids"] = [image_id]
        return obj

    def _variation_object(self, spec: ItemSpec, var: VariationSpec, item_id: str,
                          version: int | None, var_id: str | None) -> dict:
        obj: dict[str, Any] = {
            "type": "ITEM_VARIATION",
            "id": var_id or _temp_variation_id(spec, var.tier),
        }
        # The item's version, stamped on every existing variation. Checked in
        # the sandbox on 2026-10-20 (docs/qa/2026-10-20-square-variation-
        # versions-sandbox-check.md): two renames in a row after a push both
        # succeed, so Square accepts this; do not store a version per variation.
        if var_id and version is not None:
            obj["version"] = version
        obj.update({
            "present_at_all_locations": False,
            "present_at_location_ids": [self.location_id],
            "item_variation_data": {
                "item_id": item_id,
                "name": var.name,
                "sku": var.sku,
                "ordinal": var.ordinal,
                "pricing_type": "FIXED_PRICING",
                "price_money": {"amount": var.price_cents, "currency": "USD"},
            },
        })
        return obj


ENVIRONMENTS = {
    "sandbox": SquareEnvironment.SANDBOX,
    "production": SquareEnvironment.PRODUCTION,
}


def disabled_reason() -> str | None:
    """Why the sync is off, or None when every Square setting is present.

    A blank token is the deliberate off switch and is not an error. A token
    with a blank location or category ID is a misconfiguration: pushing
    would create items Square rejects, so the sync stays off and says why.
    So is an environment that is neither name: it must not quietly fall
    back to the sandbox, where a production token is refused on every call.
    """
    if not settings.SQUARE_ACCESS_TOKEN:
        return "no SQUARE_ACCESS_TOKEN"
    blank = [name for name in ("SQUARE_LOCATION_ID", "SQUARE_TICKET_CATEGORY_ID")
             if not getattr(settings, name)]
    if blank:
        verb = "is" if len(blank) == 1 else "are"
        return f"{' and '.join(blank)} {verb} blank"
    if settings.SQUARE_ENVIRONMENT not in ENVIRONMENTS:
        return (f"SQUARE_ENVIRONMENT is {settings.SQUARE_ENVIRONMENT!r}, "
                "not sandbox or production")
    return None


def square_enabled() -> bool:
    """The one answer to "is Square on?", for every page, panel and command."""
    return disabled_reason() is None


@functools.lru_cache(maxsize=4)
def _client(token: str, environment: SquareEnvironment) -> Square:
    # One client per process: it holds the connection pool, and get_gateway()
    # runs on page views. Cached on its inputs, so a settings change in a
    # test (or a token rotation after a restart) gets a fresh one.
    # The push runs inside the dashboard request; fail well before the worker does.
    return Square(token=token, environment=environment, timeout=10)


def reset_client_cache() -> None:
    _client.cache_clear()


def get_gateway() -> SquareGateway | None:
    reason = disabled_reason()
    if reason is not None:
        if settings.SQUARE_ACCESS_TOKEN:
            logger.error("Square sync disabled: %s", reason)
        return None
    client = _client(settings.SQUARE_ACCESS_TOKEN,
                     ENVIRONMENTS[settings.SQUARE_ENVIRONMENT])
    return SquareGateway(client, location_id=settings.SQUARE_LOCATION_ID,
                         category_id=settings.SQUARE_TICKET_CATEGORY_ID)
