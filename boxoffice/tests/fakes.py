"""In-memory stand-in for SquareGateway, used by every test that needs Square."""
import datetime
import itertools

from boxoffice.gateway import (
    GatewayError,
    OrderData,
    RemoteItem,
    UpsertResult,
    VersionMismatch,
)
from boxoffice.spec import ItemSpec


class FakeGateway:
    def __init__(self, *, fail_with: GatewayError | None = None) -> None:
        self.items: dict[str, RemoteItem] = {}
        self.orders: list[OrderData] = []
        self.categories: dict[str, str] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_with = fail_with
        self._item_ids = itertools.count(1)
        self._var_ids = itertools.count(1)

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
        if item_id not in self.items:
            raise GatewayError(f"Unknown item {item_id}")
        del self.items[item_id]

    def retrieve_item(self, item_id: str) -> RemoteItem:
        self._record("retrieve_item", item_id=item_id)
        if item_id not in self.items:
            raise GatewayError(f"Unknown item {item_id}")
        return self.items[item_id]

    def search_orders(self, start: datetime.datetime,
                      end: datetime.datetime) -> list[OrderData]:
        self._record("search_orders", start=start, end=end)
        return [o for o in self.orders if start <= o.closed_at < end]

    def list_ticket_items(self) -> list[RemoteItem]:
        self._record("list_ticket_items")
        return list(self.items.values())

    def lookup_categories(self, variation_ids: list[str]) -> dict[str, str]:
        self._record("lookup_categories", variation_ids=variation_ids)
        return {vid: self.categories[vid] for vid in variation_ids
                if vid in self.categories}
