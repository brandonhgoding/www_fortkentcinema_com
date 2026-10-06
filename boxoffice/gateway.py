"""The only module that talks to Square. Everything else uses these types."""
import datetime
import logging
from dataclasses import dataclass
from typing import Any, Callable, TypeVar
from uuid import uuid4

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


def _call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return fn(*args, **kwargs)
    except ApiError as exc:
        if any(getattr(e, "code", None) == "VERSION_MISMATCH" for e in exc.errors):
            raise VersionMismatch(str(exc.body)) from exc
        raise GatewayError(str(exc.body)) from exc
    except (httpx.HTTPError, pydantic.ValidationError) as exc:
        # The SDK does not wrap transport failures or unparseable responses.
        raise GatewayError(f"{type(exc).__name__}: {exc}") from exc


def _temp_item_id(spec: ItemSpec) -> str:
    return f"#eng-{spec.engagement_id}"


def _temp_variation_id(spec: ItemSpec, tier: str) -> str:
    return f"#eng-{spec.engagement_id}-{tier}"


def _category_ids(obj: Any) -> list[str]:
    return [c.id for c in (obj.item_data.categories or [])]


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
        name=line.name,
        variation_name=line.variation_name or "",
        catalog_object_id=line.catalog_object_id or "",
        quantity=int(float(line.quantity)),
        gross_cents=line.total_money.amount,
    )


def _order_data(order: Any) -> OrderData:
    return OrderData(
        order_id=order.id,
        closed_at=(datetime.datetime.fromisoformat(order.closed_at)
                   if order.closed_at else None),
        lines=tuple(_order_line(li) for li in (order.line_items or [])),
    )


class SquareGateway:
    def __init__(self, client, location_id: str, category_id: str) -> None:
        self.client = client
        self.location_id = location_id
        self.category_id = category_id

    def upsert_item(self, spec: ItemSpec, *, item_id: str | None, version: int | None,
                    variation_ids_by_tier: dict[str, str]) -> UpsertResult:
        item_obj = self._item_object(spec, item_id, version, variation_ids_by_tier)
        response = _call(self.client.catalog.batch_upsert,
                         idempotency_key=str(uuid4()),
                         batches=[{"objects": [item_obj]}])
        minted = {m.client_object_id: m.object_id for m in (response.id_mappings or [])}
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

    def delete_item(self, item_id: str) -> None:
        # batch_delete "succeeds even if only a portion of the targeted IDs can be
        # deleted" (SDK docstring), so an already-gone item does not raise.
        _call(self.client.catalog.batch_delete, object_ids=[item_id])

    def retrieve_item(self, item_id: str) -> RemoteItem:
        response = _call(self.client.catalog.object.get, item_id,
                         include_related_objects=True)
        return _remote_item(response.object)

    def search_orders(self, start: datetime.datetime,
                      end: datetime.datetime) -> list[OrderData]:
        query = {
            "filter": {
                "state_filter": {"states": ["COMPLETED"]},
                "date_time_filter": {"closed_at": {
                    "start_at": start.isoformat(), "end_at": end.isoformat()}},
            },
            "sort": {"sort_field": "CLOSED_AT", "sort_order": "ASC"},
        }
        orders: list[OrderData] = []
        page: dict[str, Any] = {}
        while True:
            response = _call(self.client.orders.search,
                             location_ids=[self.location_id], query=query, **page)
            orders.extend(_order_data(o) for o in (response.orders or []))
            if not response.cursor:
                return orders
            page = {"cursor": response.cursor}

    def list_ticket_items(self) -> list[RemoteItem]:
        objects = _call(lambda: list(self.client.catalog.list(types="ITEM")))
        return [_remote_item(obj) for obj in objects
                if self.category_id in _category_ids(obj)]

    def lookup_categories(self, variation_ids: list[str]) -> dict[str, str]:
        if not variation_ids:
            return {}
        # Deleted objects too: a hand-made item removed at cutover still sold today.
        response = _call(self.client.catalog.batch_get, object_ids=variation_ids,
                         include_related_objects=True, include_deleted_objects=True)
        item_category = {}
        for item in response.related_objects or []:
            cats = _category_ids(item)
            if cats:
                item_category[item.id] = cats[0]
        result = {}
        for var in response.objects or []:
            cat = item_category.get(var.item_variation_data.item_id)
            if cat:
                result[var.id] = cat
        return result

    def _item_object(self, spec: ItemSpec, item_id: str | None, version: int | None,
                     variation_ids_by_tier: dict[str, str]) -> dict:
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
        return obj

    def _variation_object(self, spec: ItemSpec, var: VariationSpec, item_id: str,
                          version: int | None, var_id: str | None) -> dict:
        obj: dict[str, Any] = {
            "type": "ITEM_VARIATION",
            "id": var_id or _temp_variation_id(spec, var.tier),
        }
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


def disabled_reason() -> str | None:
    """Why the sync is off, or None when every Square setting is present.

    A blank token is the deliberate off switch and is not an error. A token
    with a blank location or category ID is a misconfiguration: pushing
    would create items Square rejects, so the sync stays off and says why.
    """
    if not settings.SQUARE_ACCESS_TOKEN:
        return "no SQUARE_ACCESS_TOKEN"
    blank = [name for name in ("SQUARE_LOCATION_ID", "SQUARE_TICKET_CATEGORY_ID")
             if not getattr(settings, name)]
    if not blank:
        return None
    verb = "is" if len(blank) == 1 else "are"
    return f"{' and '.join(blank)} {verb} blank"


def get_gateway() -> SquareGateway | None:
    reason = disabled_reason()
    if reason is not None:
        if settings.SQUARE_ACCESS_TOKEN:
            logger.error("Square sync disabled: %s", reason)
        return None
    token = settings.SQUARE_ACCESS_TOKEN
    environment = (SquareEnvironment.PRODUCTION
                   if settings.SQUARE_ENVIRONMENT == "production"
                   else SquareEnvironment.SANDBOX)
    # The push runs inside the dashboard request; fail well before the worker does.
    client = Square(token=token, environment=environment, timeout=10)
    return SquareGateway(client, location_id=settings.SQUARE_LOCATION_ID,
                         category_id=settings.SQUARE_TICKET_CATEGORY_ID)
