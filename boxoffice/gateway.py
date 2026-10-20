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


class InvalidPhone(GatewayError):
    """Square could not parse the buyer phone sent as a checkout prefill."""


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
class Recipient:
    display_name: str  # each "" when Square omits it
    email_address: str
    phone_number: str


@dataclass(frozen=True)
class Tender:
    payment_id: str
    status: str  # the card status, CAPTURED when paid; "" when not a card tender


@dataclass(frozen=True)
class OrderData:
    order_id: str
    closed_at: datetime.datetime | None  # aware; None when Square omits it
    lines: tuple[OrderLine, ...]
    recipient: Recipient | None = None  # the buyer, on payment-link orders
    # When the buyer paid: the first tender's created_at, else the order's
    # created_at; aware, None when Square gives neither. Payment-link orders
    # reach COMPLETED (closed_at) only when staff mark the shipment done.
    paid_at: datetime.datetime | None = None
    tenders: tuple[Tender, ...] = ()
    reference_id: str = ""  # the website's order number on payment-link orders


@dataclass(frozen=True)
class CheckoutLine:
    variation_id: str
    name: str
    quantity: int
    unit_cents: int  # the price the buyer pays per ticket
    discount_cents: int  # the per-line matinee total; 0 for none


@dataclass(frozen=True)
class CheckoutSpec:
    reference: str
    showtime_id: int
    lines: tuple[CheckoutLine, ...]
    redirect_url: str
    buyer_email: str
    buyer_phone: str
    support_email: str
    idempotency_key: str
    customer_id: str = ""  # the buyer's Square customer; "" sends none


@dataclass(frozen=True)
class CheckoutResult:
    order_id: str
    url: str


def _call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run ``fn``, which calls Square and reads the reply, as one gateway step.

    Every way that can go wrong is a GatewayError, so callers have one thing
    to catch: the webhook answers 503, the pull marks the day FAILED, the
    ticket page shows a message. The reply is read inside too, because a
    shape this module does not expect must not escape as a bare
    AttributeError and turn into a 500.
    """
    try:
        return fn(*args, **kwargs)
    except ApiError as exc:
        codes = {getattr(e, "code", None) for e in exc.errors}
        if "VERSION_MISMATCH" in codes:
            raise VersionMismatch(str(exc.body)) from exc
        if "INVALID_PHONE_NUMBER" in codes:
            raise InvalidPhone(str(exc.body)) from exc
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
        quantity=int(float(line.quantity)),
        gross_cents=line.total_money.amount,
    )


def _recipient(order: Any) -> Recipient | None:
    for fulfillment in order.fulfillments or []:
        for kind in ("pickup_details", "shipment_details", "delivery_details"):
            recipient = getattr(getattr(fulfillment, kind, None), "recipient", None)
            if recipient is not None:
                return Recipient(*(getattr(recipient, field, None) or ""
                                   for field in ("display_name", "email_address",
                                                 "phone_number")))
    return None


def _timestamp(value: str | None) -> datetime.datetime | None:
    return datetime.datetime.fromisoformat(value) if value else None


def _paid_at(order: Any) -> datetime.datetime | None:
    tenders = order.tenders or []
    first_tender = tenders[0].created_at if tenders else None
    return _timestamp(first_tender or order.created_at)


def _tender(tender: Any) -> Tender:
    card_details = getattr(tender, "card_details", None)
    return Tender(payment_id=tender.id,
                  status=getattr(card_details, "status", None) or "")


def _order_data(order: Any) -> OrderData:
    return OrderData(
        order_id=order.id,
        closed_at=_timestamp(order.closed_at),
        lines=tuple(_order_line(li) for li in (order.line_items or [])),
        recipient=_recipient(order),
        paid_at=_paid_at(order),
        tenders=tuple(_tender(t) for t in (order.tenders or [])),
        reference_id=order.reference_id or "",
    )


def _usd(cents: int) -> dict:
    return {"amount": cents, "currency": "USD"}


def _matinee_uid(line: CheckoutLine) -> str:
    return f"matinee-{line.variation_id}"


def _checkout_line_item(line: CheckoutLine) -> dict:
    # Square prices the line at the catalog variation's price unless told
    # otherwise; the matinee discount then brings it down to unit_cents.
    if line.discount_cents % line.quantity:
        raise ValueError(
            f"Discount {line.discount_cents} is not a whole number of cents per "
            f"ticket for quantity {line.quantity}")
    item: dict[str, Any] = {
        "catalog_object_id": line.variation_id,
        "quantity": str(line.quantity),
        "base_price_money": _usd(
            line.unit_cents + line.discount_cents // line.quantity),
    }
    if line.discount_cents:
        item["applied_discounts"] = [{"discount_uid": _matinee_uid(line)}]
    return item


def payment_link_body(spec: CheckoutSpec, location_id: str) -> dict:
    """The keyword arguments for checkout.payment_links.create."""
    order: dict[str, Any] = {
        "location_id": location_id,
        "reference_id": spec.reference,
        "metadata": {"showtime": str(spec.showtime_id)},
        "line_items": [_checkout_line_item(line) for line in spec.lines],
    }
    if spec.customer_id:
        order["customer_id"] = spec.customer_id
    discounts = [
        {"uid": _matinee_uid(line), "name": "Matinee", "type": "FIXED_AMOUNT",
         "scope": "LINE_ITEM", "amount_money": _usd(line.discount_cents)}
        for line in spec.lines if line.discount_cents
    ]
    if discounts:
        order["discounts"] = discounts
    options: dict[str, Any] = {
        "redirect_url": spec.redirect_url,
        "ask_for_shipping_address": False,
        "allow_tipping": False,
        "accepted_payment_methods": {"apple_pay": True, "google_pay": True},
    }
    # Leave out a blank support email or phone rather than send Square "".
    if spec.support_email:
        options["merchant_support_email"] = spec.support_email
    prefill = {"buyer_email": spec.buyer_email}
    if spec.buyer_phone:
        prefill["buyer_phone_number"] = spec.buyer_phone
    return {
        "idempotency_key": spec.idempotency_key,
        "order": order,
        "checkout_options": options,
        "pre_populated_data": prefill,
    }


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
                idempotency_key=str(uuid4()), batches=[{"objects": [item_obj]}])
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
        return _call(lambda: _remote_item(
            self.client.catalog.object.get(item_id, include_related_objects=True)
            .object))

    def search_orders(self, start: datetime.datetime,
                      end: datetime.datetime) -> list[OrderData]:
        """Orders closed in [start, end): the register's completed sales."""
        return self._search("COMPLETED", "closed_at", start, end)

    def search_open_orders(self, start: datetime.datetime,
                           end: datetime.datetime) -> list[OrderData]:
        """Orders still OPEN that were touched in [start, end).

        A paid payment-link order stays OPEN (Square adds a digital
        fulfillment nobody completes), so it never has a closed_at. Square
        cannot filter by reference, so this returns every open order updated
        in the window, paid or not; the caller keeps the ones it wants.
        """
        return self._search("OPEN", "updated_at", start, end)

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

    def retrieve_order(self, order_id: str) -> OrderData:
        return _call(lambda: _order_data(self.client.orders.get(order_id).order))

    def create_payment_link(self, spec: CheckoutSpec) -> CheckoutResult:
        # Built first: a bad spec is a programming error, not a gateway one.
        body = payment_link_body(spec, self.location_id)

        def create() -> CheckoutResult:
            link = self.client.checkout.payment_links.create(**body).payment_link
            return CheckoutResult(order_id=link.order_id, url=link.url)

        return _call(create)

    def find_customer(self, email: str) -> str | None:
        """The id of the customer whose email is exactly ``email``, if any."""
        def search() -> str | None:
            response = self.client.customers.search(
                query={"filter": {"email_address": {"exact": email}}}, limit=1)
            customers = response.customers or []
            return customers[0].id if customers else None

        return _call(search)

    def create_customer(self, *, given_name: str, family_name: str, email: str,
                        phone: str, idempotency_key: str) -> str:
        """Make a customer profile and return its id. ``phone`` is E.164 or ""."""
        # Square rejects an empty string for the optional fields; omit them.
        fields = {"given_name": given_name, "family_name": family_name,
                  "email_address": email, "phone_number": phone}
        return _call(lambda: self.client.customers.create(
            idempotency_key=idempotency_key,
            **{k: v for k, v in fields.items() if v}).customer.id)

    def refund_payment(self, *, payment_id: str, amount_cents: int,
                       idempotency_key: str, reason: str) -> str:
        return _call(lambda: self.client.refunds.refund_payment(
            idempotency_key=idempotency_key, payment_id=payment_id,
            amount_money=_usd(amount_cents), reason=reason).refund.id)

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
                "idempotency_key": str(uuid4()),
                "object_id": item_id,
                "is_primary": True,
                "image": {"type": "IMAGE", "id": "#poster",
                          "image_data": {"name": name}},
            },
            image_file=("poster.jpg", image, "image/jpeg"),
        ).image.id)

    def lookup_categories(self, variation_ids: list[str]) -> dict[str, str]:
        if not variation_ids:
            return {}

        def lookup() -> dict[str, str]:
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

        return _call(lookup)

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


def get_gateway() -> SquareGateway | None:
    reason = disabled_reason()
    if reason is not None:
        if settings.SQUARE_ACCESS_TOKEN:
            logger.error("Square sync disabled: %s", reason)
        return None
    token = settings.SQUARE_ACCESS_TOKEN
    environment = ENVIRONMENTS[settings.SQUARE_ENVIRONMENT]
    # The push runs inside the dashboard request; fail well before the worker does.
    client = Square(token=token, environment=environment, timeout=10)
    return SquareGateway(client, location_id=settings.SQUARE_LOCATION_ID,
                         category_id=settings.SQUARE_TICKET_CATEGORY_ID)
