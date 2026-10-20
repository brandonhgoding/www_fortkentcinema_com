"""In-memory stand-in for SquareGateway, used by every test that needs Square."""
import dataclasses
import datetime
import itertools

from boxoffice.gateway import (
    CheckoutResult,
    CheckoutSpec,
    GatewayError,
    InvalidPhone,
    OrderData,
    OrderLine,
    RemoteItem,
    Tender,
    UpsertResult,
    VersionMismatch,
)
from boxoffice.spec import ItemSpec


class FakeGateway:
    def __init__(self, *, fail_with: GatewayError | None = None,
                 fail_on: set[str] | None = None, reject_phone: bool = False) -> None:
        self.items: dict[str, RemoteItem] = {}
        self.orders: list[OrderData] = []
        self.categories: dict[str, str] = {}
        self.images: dict[str, tuple[str, bytes]] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_with = fail_with
        # Payment IDs whose refund_payment raises GatewayError("boom").
        self.fail_on: set[str] = set() if fail_on is None else fail_on
        # Like Square: a payment link with a phone it cannot parse is refused.
        self.reject_phone = reject_phone
        self._item_ids = itertools.count(1)
        self._var_ids = itertools.count(1)
        self._image_ids = itertools.count(1)
        self._link_ids = itertools.count(1)
        self._refund_ids = itertools.count(1)

    def _record(self, method: str, **kwargs) -> None:
        self.calls.append((method, kwargs))
        if self.fail_with is not None:
            raise self.fail_with

    def upsert_item(self, spec: ItemSpec, *, item_id: str | None, version: int | None,
                    variation_ids_by_tier: dict[str, str]) -> UpsertResult:
        self._record("upsert_item", spec=spec, item_id=item_id, version=version,
                     variation_ids_by_tier=variation_ids_by_tier)
        if item_id is None:
            item_id = f"item-{next(self._item_ids)}"
            new_version = 1
        else:
            stored = self.items.get(item_id)
            if stored is None:
                raise GatewayError(f"Unknown item {item_id}")
            if version is not None and version != stored.version:
                raise VersionMismatch(
                    f"Item {item_id} is at version {stored.version}, not {version}")
            new_version = stored.version + 1
        ids_by_tier = {
            v.tier: variation_ids_by_tier.get(v.tier) or f"var-{next(self._var_ids)}"
            for v in spec.variations
        }
        self.items[item_id] = RemoteItem(
            item_id=item_id, version=new_version, name=spec.name,
            variation_ids_by_sku={v.sku: ids_by_tier[v.tier] for v in spec.variations},
        )
        return UpsertResult(item_id=item_id, version=new_version,
                            variation_ids_by_tier=ids_by_tier)

    def delete_item(self, item_id: str) -> None:
        self._record("delete_item", item_id=item_id)
        # Like Square's batch_delete, an unknown id succeeds silently.
        self.items.pop(item_id, None)
        self.images.pop(item_id, None)

    def retrieve_item(self, item_id: str) -> RemoteItem:
        self._record("retrieve_item", item_id=item_id)
        if item_id not in self.items:
            raise GatewayError(f"Unknown item {item_id}")
        return self.items[item_id]

    def search_orders(self, start: datetime.datetime,
                      end: datetime.datetime) -> list[OrderData]:
        self._record("search_orders", start=start, end=end)
        # Only closed orders, like the real COMPLETED state filter.
        return [o for o in self.orders
                if o.closed_at is not None and start <= o.closed_at < end]

    def retrieve_order(self, order_id: str) -> OrderData:
        self._record("retrieve_order", order_id=order_id)
        for order in self.orders:
            if order.order_id == order_id:
                return order
        raise GatewayError(f"Unknown order {order_id}")

    def create_payment_link(self, spec: CheckoutSpec) -> CheckoutResult:
        self._record("create_payment_link", spec=spec)
        if self.reject_phone and spec.buyer_phone:
            raise InvalidPhone("INVALID_PHONE_NUMBER")
        n = next(self._link_ids)
        order_id = f"SQ-{n}"
        lines = tuple(
            OrderLine(uid=f"{order_id}-{i}", name=line.name, variation_name=line.name,
                      catalog_object_id=line.variation_id, quantity=line.quantity,
                      gross_cents=line.unit_cents * line.quantity)
            for i, line in enumerate(spec.lines)
        )
        self.orders.append(OrderData(order_id=order_id, closed_at=None, lines=lines))
        return CheckoutResult(order_id=order_id, url=f"https://square.link/u/{n}")

    def refund_payment(self, *, payment_id: str, amount_cents: int,
                       idempotency_key: str, reason: str) -> str:
        self._record("refund_payment", payment_id=payment_id,
                     amount_cents=amount_cents, idempotency_key=idempotency_key,
                     reason=reason)
        if payment_id in self.fail_on:
            raise GatewayError("boom")
        return f"R-{next(self._refund_ids)}"

    def pay(self, order_id: str, payment_id: str = "P1") -> None:
        """Test helper: the buyer completes the payment link's checkout."""
        for i, order in enumerate(self.orders):
            if order.order_id == order_id:
                self.orders[i] = dataclasses.replace(
                    order, tenders=(Tender(payment_id, "CAPTURED"),),
                    paid_at=datetime.datetime.now(datetime.timezone.utc))
                return
        raise GatewayError(f"Unknown order {order_id}")

    def list_ticket_items(self) -> list[RemoteItem]:
        self._record("list_ticket_items")
        return list(self.items.values())

    def upload_item_image(self, item_id: str, image: bytes, name: str) -> str:
        self._record("upload_item_image", item_id=item_id, image=image, name=name)
        if item_id not in self.items:
            raise GatewayError(f"Unknown item {item_id}")
        image_id = f"img-{next(self._image_ids)}"
        self.images[image_id] = (item_id, image)
        return image_id

    def lookup_categories(self, variation_ids: list[str]) -> dict[str, str]:
        self._record("lookup_categories", variation_ids=variation_ids)
        return {vid: self.categories[vid] for vid in variation_ids
                if vid in self.categories}
