import dataclasses
import datetime
import inspect
from unittest import mock

import httpx
import pydantic

import boxoffice.gateway as gateway_module
from boxoffice.gateway import (
    GatewayError,
    NotFound,
    OrderData,
    OrderLine,
    RemoteItem,
    SquareGateway,
    Tender,
    UpsertResult,
    VersionMismatch,
    Gateway,
    _order_data,
    disabled_reason,
    parse_timestamp,
    square_enabled,
    get_gateway,
)
from boxoffice.spec import ItemSpec, VariationSpec
from boxoffice.tests.fakes import FakeGateway
from django.test import SimpleTestCase, override_settings
from square.core.api_error import ApiError
from square.environment import SquareEnvironment

TIERS = ["adult", "senior", "child", "matinee", "member"]
PRICES = [800, 700, 600, 600, 400]

SPEC_FOR_7 = ItemSpec(
    engagement_id=7,
    name="Dune",
    variations=tuple(
        VariationSpec(tier=t, name=t.title(), sku=f"fkc-eng-7-{t}",
                      price_cents=p, ordinal=i)
        for i, (t, p) in enumerate(zip(TIERS, PRICES))
    ),
)

START = datetime.datetime(2026, 10, 4, 4, 0, tzinfo=datetime.timezone.utc)
END = datetime.datetime(2026, 10, 5, 4, 0, tzinfo=datetime.timezone.utc)


def _upsert_response(mappings: list[tuple[str, str]], version: int) -> mock.Mock:
    return mock.Mock(
        id_mappings=[mock.Mock(client_object_id=c, object_id=o) for c, o in mappings],
        objects=[mock.Mock(version=version)],
    )


def _line(uid: str = "L1", catalog_object_id: str | None = "V0",
          quantity: str = "1.00000000", variation_name: str | None = "Adult",
          amount: int = 800) -> mock.Mock:
    line = mock.Mock(uid=uid, variation_name=variation_name,
                     catalog_object_id=catalog_object_id, quantity=quantity,
                     total_money=mock.Mock(amount=amount))
    line.name = "Dune"
    return line


def _tender(payment_id: str, *, type: str = "CARD", amount: int | None = 1600,
            card_details=None, bank_account_details=None,
            buy_now_pay_later_details=None, square_account_details=None) -> mock.Mock:
    # A Mock invents missing attributes, so every details block is explicit.
    return mock.Mock(id=payment_id, created_at="2026-10-03T03:12:00Z", type=type,
                     amount_money=None if amount is None else mock.Mock(amount=amount),
                     card_details=card_details,
                     bank_account_details=bank_account_details,
                     buy_now_pay_later_details=buy_now_pay_later_details,
                     square_account_details=square_account_details)


def _order(order_id: str, closed_at: str, lines: list[mock.Mock],
           tenders: list[mock.Mock] | None = None,
           created_at: str | None = None,
           reference_id: str | None = None,
           metadata: dict[str, str] | None = None) -> mock.Mock:
    # A Mock invents missing attributes, so "absent" must be an explicit None.
    return mock.Mock(id=order_id, closed_at=closed_at, line_items=lines,
                     tenders=tenders,
                     created_at=created_at, reference_id=reference_id,
                     metadata=metadata)


def _catalog_item(item_id: str, cats: list[str] | None) -> mock.Mock:
    obj = mock.Mock(id=item_id, version=1)
    obj.item_data.name = item_id
    obj.item_data.categories = None if cats is None else [mock.Mock(id=c) for c in cats]
    obj.item_data.variations = [
        mock.Mock(id=f"{item_id}-v", item_variation_data=mock.Mock(sku="s"))]
    return obj


class UpsertRequestTests(SimpleTestCase):
    def test_create_builds_temp_ids_and_five_variations(self) -> None:
        client = mock.Mock()
        client.catalog.batch_upsert.return_value = _upsert_response(
            [("#eng-7", "I1")]
            + [(f"#eng-7-{t}", f"V{i}") for i, t in enumerate(TIERS)],
            version=3)
        gw = SquareGateway(client, location_id="LOC", category_id="CAT")
        result = gw.upsert_item(SPEC_FOR_7, item_id=None, version=None,
                                variation_ids_by_tier={})
        kwargs = client.catalog.batch_upsert.call_args.kwargs
        self.assertTrue(kwargs["idempotency_key"])
        item = kwargs["batches"][0]["objects"][0]
        self.assertEqual(item["type"], "ITEM")
        self.assertEqual(item["id"], "#eng-7")
        self.assertNotIn("version", item)
        self.assertFalse(item["present_at_all_locations"])
        self.assertEqual(item["present_at_location_ids"], ["LOC"])
        self.assertEqual(item["item_data"]["name"], "Dune")
        self.assertEqual(item["item_data"]["product_type"], "REGULAR")
        self.assertEqual(item["item_data"]["categories"], [{"id": "CAT"}])
        self.assertEqual(item["item_data"]["reporting_category"], {"id": "CAT"})
        self.assertFalse(item["item_data"]["is_taxable"])
        variations = item["item_data"]["variations"]
        self.assertEqual([v["id"] for v in variations],
                         [f"#eng-7-{t}" for t in TIERS])
        first = variations[0]
        self.assertEqual(first["type"], "ITEM_VARIATION")
        self.assertNotIn("version", first)
        self.assertFalse(first["present_at_all_locations"])
        self.assertEqual(first["present_at_location_ids"], ["LOC"])
        data = first["item_variation_data"]
        self.assertEqual(data["item_id"], "#eng-7")
        self.assertEqual(data["name"], "Adult")
        self.assertEqual(data["sku"], "fkc-eng-7-adult")
        self.assertEqual(data["ordinal"], 0)
        self.assertEqual(data["pricing_type"], "FIXED_PRICING")
        self.assertEqual(data["price_money"], {"amount": 800, "currency": "USD"})
        self.assertEqual(variations[4]["item_variation_data"]["price_money"],
                         {"amount": 400, "currency": "USD"})
        self.assertEqual(result, UpsertResult(
            "I1", 3, {"adult": "V0", "senior": "V1", "child": "V2",
                      "matinee": "V3", "member": "V4"}))

    def test_update_sends_stored_ids_and_version(self) -> None:
        client = mock.Mock()
        client.catalog.batch_upsert.return_value = _upsert_response([], version=4)
        stored = {t: f"V{i}" for i, t in enumerate(TIERS)}
        gw = SquareGateway(client, location_id="LOC", category_id="CAT")
        result = gw.upsert_item(SPEC_FOR_7, item_id="I1", version=3,
                                variation_ids_by_tier=stored)
        item = client.catalog.batch_upsert.call_args.kwargs["batches"][0]["objects"][0]
        self.assertEqual(item["id"], "I1")
        self.assertEqual(item["version"], 3)
        variations = item["item_data"]["variations"]
        self.assertEqual([v["id"] for v in variations], [f"V{i}" for i in range(5)])
        self.assertEqual([v["version"] for v in variations], [3] * 5)
        self.assertEqual({v["item_variation_data"]["item_id"] for v in variations},
                         {"I1"})
        self.assertEqual(result, UpsertResult("I1", 4, stored))

    def test_update_sends_the_item_image_so_square_keeps_it(self) -> None:
        # Catalog updates replace the whole object: an item sent without its
        # image_ids loses the poster from the register tile.
        client = mock.Mock()
        client.catalog.batch_upsert.return_value = _upsert_response([], version=4)
        stored = {t: f"V{i}" for i, t in enumerate(TIERS)}
        gw = SquareGateway(client, "LOC", "CAT")
        gw.upsert_item(SPEC_FOR_7, item_id="I1", version=3,
                       variation_ids_by_tier=stored, image_id="IMG1")
        item = client.catalog.batch_upsert.call_args.kwargs["batches"][0]["objects"][0]
        self.assertEqual(item["item_data"]["image_ids"], ["IMG1"])
        gw.upsert_item(SPEC_FOR_7, item_id="I1", version=4,
                       variation_ids_by_tier=stored)
        item = client.catalog.batch_upsert.call_args.kwargs["batches"][0]["objects"][0]
        self.assertNotIn("image_ids", item["item_data"])

    def test_update_with_missing_tier_mints_temp_id_for_it(self) -> None:
        client = mock.Mock()
        client.catalog.batch_upsert.return_value = _upsert_response(
            [("#eng-7-member", "V9")], version=4)
        stored = {t: f"V{i}" for i, t in enumerate(TIERS[:4])}
        result = SquareGateway(client, "LOC", "CAT").upsert_item(
            SPEC_FOR_7, item_id="I1", version=3, variation_ids_by_tier=stored)
        item = client.catalog.batch_upsert.call_args.kwargs["batches"][0]["objects"][0]
        member = item["item_data"]["variations"][4]
        self.assertEqual(member["id"], "#eng-7-member")
        self.assertNotIn("version", member)
        self.assertEqual(result.variation_ids_by_tier, {**stored, "member": "V9"})

    def test_version_mismatch_is_typed(self) -> None:
        client = mock.Mock()
        client.catalog.batch_upsert.side_effect = ApiError(
            status_code=400,
            body={"errors": [{"code": "VERSION_MISMATCH", "detail": "x"}]})
        with self.assertRaises(VersionMismatch):
            SquareGateway(client, "LOC", "CAT").upsert_item(
                SPEC_FOR_7, item_id="I1", version=1, variation_ids_by_tier={})

    def test_not_found_is_typed(self) -> None:
        # Only a real 404 may be read as "gone"; a 5xx is "ask again later".
        client = mock.Mock()
        client.catalog.object.get.side_effect = ApiError(
            status_code=404, body={"errors": [{"code": "NOT_FOUND"}]})
        with self.assertRaises(NotFound):
            SquareGateway(client, "LOC", "CAT").retrieve_item("I1")
        client.catalog.object.get.side_effect = ApiError(
            status_code=500, body={"errors": [{"code": "INTERNAL_SERVER_ERROR"}]})
        with self.assertRaises(GatewayError) as ctx:
            SquareGateway(client, "LOC", "CAT").retrieve_item("I1")
        self.assertNotIsInstance(ctx.exception, NotFound)

    def test_other_api_error_is_gateway_error(self) -> None:
        client = mock.Mock()
        client.catalog.batch_upsert.side_effect = ApiError(
            status_code=500, body={"errors": [{"code": "INTERNAL_SERVER_ERROR"}]})
        with self.assertRaises(GatewayError) as ctx:
            SquareGateway(client, "LOC", "CAT").upsert_item(
                SPEC_FOR_7, item_id=None, version=None, variation_ids_by_tier={})
        self.assertNotIsInstance(ctx.exception, VersionMismatch)
        self.assertIn("INTERNAL_SERVER_ERROR", str(ctx.exception))


class TransportErrorTests(SimpleTestCase):
    def test_timeout_is_gateway_error(self) -> None:
        client = mock.Mock()
        client.catalog.batch_upsert.side_effect = httpx.ReadTimeout("slow")
        with self.assertRaisesMessage(GatewayError, "slow"):
            SquareGateway(client, "LOC", "CAT").upsert_item(
                SPEC_FOR_7, item_id=None, version=None, variation_ids_by_tier={})

    def test_connection_error_during_paging_is_gateway_error(self) -> None:
        client = mock.Mock()

        def pages():
            yield _catalog_item("T1", ["CAT"])
            raise httpx.ConnectError("refused")

        client.catalog.list.return_value = pages()
        with self.assertRaisesMessage(GatewayError, "refused"):
            SquareGateway(client, "LOC", "CAT").list_ticket_items()

    def test_unparseable_response_is_gateway_error(self) -> None:
        class Strict(pydantic.BaseModel):
            n: int

        try:
            Strict(n="x")
        except pydantic.ValidationError as exc:
            invalid = exc
        client = mock.Mock()
        client.orders.search.side_effect = invalid
        with self.assertRaises(GatewayError):
            SquareGateway(client, "LOC", "CAT").search_orders(START, END)


class CatalogCallTests(SimpleTestCase):
    def test_delete_item_batch_deletes_the_id(self) -> None:
        client = mock.Mock()
        SquareGateway(client, "LOC", "CAT").delete_item("I1")
        client.catalog.batch_delete.assert_called_once_with(object_ids=["I1"])

    def test_delete_error_is_gateway_error(self) -> None:
        client = mock.Mock()
        client.catalog.batch_delete.side_effect = ApiError(status_code=404, body={})
        with self.assertRaises(GatewayError):
            SquareGateway(client, "LOC", "CAT").delete_item("I1")

    def test_retrieve_item_reads_version_name_and_skus(self) -> None:
        client = mock.Mock()
        obj = mock.Mock(id="I1", version=5)
        obj.item_data.name = "Dune"
        obj.item_data.variations = [
            mock.Mock(id="V0", item_variation_data=mock.Mock(sku="fkc-eng-7-adult")),
            mock.Mock(id="V1", item_variation_data=mock.Mock(sku="fkc-eng-7-senior")),
        ]
        client.catalog.object.get.return_value = mock.Mock(object=obj)
        item = SquareGateway(client, "LOC", "CAT").retrieve_item("I1")
        # Variations are embedded in the item; related objects are never read.
        client.catalog.object.get.assert_called_once_with("I1")
        self.assertEqual(item, RemoteItem(
            "I1", 5, "Dune", {"fkc-eng-7-adult": "V0", "fkc-eng-7-senior": "V1"}))

    def test_list_ticket_items_keeps_only_category_items(self) -> None:
        client = mock.Mock()
        client.catalog.list.return_value = iter([
            _catalog_item("T1", ["CAT"]), _catalog_item("P1", ["POP"]),
            _catalog_item("N1", None), _catalog_item("T2", ["X", "CAT"])])
        items = SquareGateway(client, "LOC", "CAT").list_ticket_items()
        client.catalog.list.assert_called_once_with(types="ITEM")
        self.assertEqual([i.item_id for i in items], ["T1", "T2"])
        self.assertEqual(items[0], RemoteItem("T1", 1, "T1", {"s": "T1-v"}))

    def test_lookup_categories_maps_variation_to_item_category(self) -> None:
        client = mock.Mock()
        client.catalog.batch_get.return_value = mock.Mock(
            objects=[
                mock.Mock(id="V1", item_variation_data=mock.Mock(item_id="I1")),
                mock.Mock(id="V2", item_variation_data=mock.Mock(item_id="I2")),
                mock.Mock(id="V3", item_variation_data=mock.Mock(item_id="I3")),
            ],
            related_objects=[_catalog_item("I1", ["CAT"]), _catalog_item("I2", ["POP"]),
                             _catalog_item("I3", None)],
        )
        result = SquareGateway(client, "LOC", "CAT").lookup_categories(
            ["V1", "V2", "V3"])
        client.catalog.batch_get.assert_called_once_with(
            object_ids=["V1", "V2", "V3"], include_related_objects=True,
            include_deleted_objects=True)
        self.assertEqual(result, {"V1": "CAT", "V2": "POP"})

    def test_lookup_categories_ignores_related_objects_that_are_not_items(self) -> None:
        # Square returns every related object type (images, categories, taxes);
        # a pydantic model without item_data raises AttributeError, as a real
        # CatalogObjectImage did on the first production pull.
        image = mock.Mock(spec=["id", "type"])
        image.id, image.type = "IMG1", "IMAGE"
        stray = mock.Mock(spec=["id", "type"])  # an object id that is not a variation
        stray.id, stray.type = "X1", "CATEGORY"
        client = mock.Mock()
        client.catalog.batch_get.return_value = mock.Mock(
            objects=[mock.Mock(id="V1", item_variation_data=mock.Mock(item_id="I1")),
                     stray],
            related_objects=[image, _catalog_item("I1", ["CAT"])],
        )
        result = SquareGateway(client, "LOC", "CAT").lookup_categories(["V1", "X1"])
        self.assertEqual(result, {"V1": "CAT"})

    def test_variation_without_sku_is_left_out(self) -> None:
        obj = _catalog_item("H1", ["CAT"])
        obj.item_data.variations = [
            mock.Mock(id="H1-a", item_variation_data=mock.Mock(sku=None)),
            mock.Mock(id="H1-b", item_variation_data=mock.Mock(sku="")),
            mock.Mock(id="H1-c", item_variation_data=mock.Mock(sku="s"))]
        client = mock.Mock()
        client.catalog.list.return_value = iter([obj])
        [item] = SquareGateway(client, "LOC", "CAT").list_ticket_items()
        self.assertEqual(item.variation_ids_by_sku, {"s": "H1-c"})
        self.assertNotIn(None, item.variation_ids_by_sku)

    def test_upload_item_image_attaches_primary_image_and_returns_id(self) -> None:
        client = mock.Mock()
        client.catalog.images.create.return_value = mock.Mock(
            image=mock.Mock(id="IMG1"))
        image_id = SquareGateway(client, "LOC", "CAT").upload_item_image(
            "I1", b"jpegbytes", "Dune")
        self.assertEqual(image_id, "IMG1")
        kwargs = client.catalog.images.create.call_args.kwargs
        request = kwargs["request"]
        self.assertEqual(request["object_id"], "I1")
        self.assertTrue(request["is_primary"])
        self.assertTrue(request["idempotency_key"])
        self.assertEqual(request["image"]["type"], "IMAGE")
        self.assertEqual(request["image"]["image_data"]["name"], "Dune")
        self.assertEqual(kwargs["image_file"],
                         ("poster.jpg", b"jpegbytes", "image/jpeg"))

    def test_upload_item_image_translates_api_errors(self) -> None:
        client = mock.Mock()
        client.catalog.images.create.side_effect = ApiError(
            status_code=400, body={"errors": [{"code": "INVALID_VALUE"}]})
        with self.assertRaises(GatewayError):
            SquareGateway(client, "LOC", "CAT").upload_item_image("I1", b"x", "Dune")

    def test_lookup_categories_asks_in_batches_of_a_thousand(self) -> None:
        client = mock.Mock()
        client.catalog.batch_get.side_effect = [
            mock.Mock(objects=[mock.Mock(id="V1",
                                         item_variation_data=mock.Mock(item_id="I1"))],
                      related_objects=[_catalog_item("I1", ["CAT"])]),
            mock.Mock(objects=[mock.Mock(id="V1001",
                                         item_variation_data=mock.Mock(item_id="I2"))],
                      related_objects=[_catalog_item("I2", ["POP"])]),
        ]
        ids = [f"V{i}" for i in range(1, 1002)]
        result = SquareGateway(client, "LOC", "CAT").lookup_categories(ids)
        sent = [c.kwargs["object_ids"] for c in client.catalog.batch_get.call_args_list]
        self.assertEqual([len(s) for s in sent], [1000, 1])
        self.assertEqual(sent[0][0], "V1")
        self.assertEqual(sent[1], ["V1001"])
        self.assertEqual(result, {"V1": "CAT", "V1001": "POP"})

    def test_upsert_idempotency_key_repeats_for_the_same_request(self) -> None:
        # A timeout-then-retry must not mint a second item in Square.
        def key(version: int) -> str:
            client = mock.Mock()
            client.catalog.batch_upsert.return_value = _upsert_response([], version)
            SquareGateway(client, "LOC", "CAT").upsert_item(
                SPEC_FOR_7, item_id="I1", version=version,
                variation_ids_by_tier={t: f"V{i}" for i, t in enumerate(TIERS)})
            return client.catalog.batch_upsert.call_args.kwargs["idempotency_key"]
        self.assertEqual(key(4), key(4))
        self.assertNotEqual(key(4), key(5))
        self.assertLessEqual(len(key(4)), 128)

    def test_upload_idempotency_key_repeats_for_the_same_poster(self) -> None:
        def key(image: bytes) -> str:
            client = mock.Mock()
            client.catalog.images.create.return_value = mock.Mock(
                image=mock.Mock(id="IMG1"))
            SquareGateway(client, "LOC", "CAT").upload_item_image(
                "I1", image, "Dune")
            return client.catalog.images.create.call_args.kwargs["request"][
                "idempotency_key"]
        self.assertEqual(key(b"jpeg"), key(b"jpeg"))
        self.assertNotEqual(key(b"jpeg"), key(b"other"))

    def test_lookup_categories_with_no_ids_makes_no_call(self) -> None:
        client = mock.Mock()
        self.assertEqual(SquareGateway(client, "LOC", "CAT").lookup_categories([]), {})
        client.catalog.batch_get.assert_not_called()


class ResponseShapeTests(SimpleTestCase):
    """A response the SDK parsed but this module cannot read is a GatewayError.

    Callers branch on GatewayError (the pull marks the day FAILED, the sync
    records the error); a bare AttributeError
    from a surprising shape would be a 500 instead.
    """

    def test_search_line_without_total_money_is_gateway_error(self) -> None:
        line = _line()
        line.total_money = None
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", "2026-10-04T18:00:00Z", [line])], cursor=None)
        with self.assertRaisesMessage(GatewayError, "AttributeError"):
            SquareGateway(client, "LOC", "CAT").search_orders(START, END)

    def test_searched_order_with_bad_timestamp_is_gateway_error(self) -> None:
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", "yesterday", [_line()])], cursor=None)
        with self.assertRaisesMessage(GatewayError, "ValueError"):
            SquareGateway(client, "LOC", "CAT").search_orders(START, END)

    def test_upsert_without_id_mappings_is_gateway_error(self) -> None:
        client = mock.Mock()
        client.catalog.batch_upsert.return_value = mock.Mock(
            id_mappings=[], objects=[mock.Mock(version=1)])
        with self.assertRaisesMessage(GatewayError, "KeyError"):
            SquareGateway(client, "LOC", "CAT").upsert_item(
                SPEC_FOR_7, item_id=None, version=None, variation_ids_by_tier={})


class SearchOrdersTests(SimpleTestCase):
    def test_filters_completed_by_closed_at_and_pages(self) -> None:
        client = mock.Mock()
        client.orders.search.side_effect = [
            mock.Mock(orders=[_order("O1", "2026-10-04T18:00:00Z", [_line()])],
                      cursor="page2"),
            mock.Mock(orders=[_order("O2", "2026-10-04T20:30:00.123Z",
                                     [_line("L2")])],
                      cursor=None),
        ]
        orders = SquareGateway(client, "LOC", "CAT").search_orders(START, END)
        self.assertEqual(client.orders.search.call_count, 2)
        first, second = client.orders.search.call_args_list
        self.assertEqual(first.kwargs["location_ids"], ["LOC"])
        query = first.kwargs["query"]
        self.assertEqual(query["filter"]["state_filter"], {"states": ["COMPLETED"]})
        self.assertEqual(query["filter"]["date_time_filter"]["closed_at"], {
            "start_at": START.isoformat(), "end_at": END.isoformat()})
        self.assertEqual(query["sort"],
                         {"sort_field": "CLOSED_AT", "sort_order": "ASC"})
        self.assertNotIn("cursor", first.kwargs)
        self.assertEqual(second.kwargs["cursor"], "page2")
        self.assertEqual(second.kwargs["query"], query)
        self.assertEqual([o.order_id for o in orders], ["O1", "O2"])
        self.assertEqual(orders[0], OrderData(
            order_id="O1",
            closed_at=datetime.datetime(2026, 10, 4, 18, 0,
                                        tzinfo=datetime.timezone.utc),
            lines=(OrderLine(uid="L1", name="Dune", variation_name="Adult",
                             catalog_object_id="V0", quantity=1, gross_cents=800),),
        ))
        self.assertIsNotNone(orders[1].closed_at.tzinfo)

    def test_search_open_orders_filters_open_by_updated_at(self) -> None:
        # Square cannot filter orders by reference, so the pull asks for every
        # OPEN order touched in the window and keeps the paid website ones.
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", None, [_line()], reference_id="FK-ABCDE")],
            cursor=None)
        orders = SquareGateway(client, "LOC", "CAT").search_open_orders(START, END)
        query = client.orders.search.call_args.kwargs["query"]
        self.assertEqual(query["filter"]["state_filter"], {"states": ["OPEN"]})
        self.assertEqual(query["filter"]["date_time_filter"], {"updated_at": {
            "start_at": START.isoformat(), "end_at": END.isoformat()}})
        self.assertEqual(query["sort"],
                         {"sort_field": "UPDATED_AT", "sort_order": "ASC"})
        self.assertEqual(client.orders.search.call_args.kwargs["location_ids"],
                         ["LOC"])
        self.assertEqual([(o.order_id, o.closed_at, o.reference_id) for o in orders],
                         [("O1", None, "FK-ABCDE")])

    def test_order_data_reads_the_showtime_from_metadata(self) -> None:
        # Website orders carried metadata.showtime; Square hands it back, so
        # the ledger need not ask the website.
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(orders=[
            _order("O1", None, [_line()], metadata={"showtime": "5"}),
            _order("O2", None, [_line()]),
            _order("O3", None, [_line()], metadata={"showtime": "soon"}),
        ], cursor=None)
        orders = SquareGateway(client, "LOC", "CAT").search_open_orders(START, END)
        self.assertEqual([o.showtime_id for o in orders], [5, None, None])

    def test_order_without_reference_has_blank_reference_id(self) -> None:
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", "2026-10-04T18:00:00Z", [_line()])], cursor=None)
        [o] = SquareGateway(client, "LOC", "CAT").search_orders(START, END)
        self.assertEqual(o.reference_id, "")

    def test_empty_page_returns_no_orders(self) -> None:
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(orders=None, cursor=None)
        gw = SquareGateway(client, "LOC", "CAT")
        self.assertEqual(gw.search_orders(START, END), [])

    def test_line_without_catalog_id_has_blank_id(self) -> None:
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", "2026-10-04T18:00:00Z",
                           [_line(catalog_object_id=None, variation_name=None)])],
            cursor=None)
        gw = SquareGateway(client, "LOC", "CAT")
        line = gw.search_orders(START, END)[0].lines[0]
        self.assertEqual(line.catalog_object_id, "")
        self.assertEqual(line.variation_name, "")

    def test_custom_amount_line_without_name_is_labelled(self) -> None:
        # A register "custom amount" charge (item_type CUSTOM_AMOUNT) carries
        # no name at all, and the ledger column is not nullable.
        line = _line(catalog_object_id=None, variation_name=None)
        line.name = None
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", "2026-10-04T18:00:00Z", [line])], cursor=None)
        gw = SquareGateway(client, "LOC", "CAT")
        self.assertEqual(gw.search_orders(START, END)[0].lines[0].name,
                         "Custom amount")

    def test_quantity_string_becomes_int(self) -> None:
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", "2026-10-04T18:00:00Z",
                           [_line(quantity="2.00000000", amount=1600)])],
            cursor=None)
        gw = SquareGateway(client, "LOC", "CAT")
        line = gw.search_orders(START, END)[0].lines[0]
        self.assertEqual(line.quantity, 2)
        self.assertIsInstance(line.quantity, int)
        self.assertEqual(line.gross_cents, 1600)

    def test_weighed_quantity_is_rounded_not_truncated(self) -> None:
        # A weighed concession line ("1.5" lb) counts as its nearest whole
        # unit; truncating would drop the count while the gross stayed right.
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", "2026-10-04T18:00:00Z",
                           [_line(uid="L1", quantity="1.50000000", amount=900),
                            _line(uid="L2", quantity="1.49000000", amount=890)])],
            cursor=None)
        lines = SquareGateway(client, "LOC", "CAT").search_orders(START, END)[0].lines
        self.assertEqual([ln.quantity for ln in lines], [2, 1])

    def test_order_without_closed_at_has_none(self) -> None:
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", None, [_line()])], cursor=None)
        [o] = SquareGateway(client, "LOC", "CAT").search_orders(START, END)
        self.assertIsNone(o.closed_at)
        self.assertEqual(o.order_id, "O1")

    def test_api_error_is_gateway_error(self) -> None:
        client = mock.Mock()
        client.orders.search.side_effect = ApiError(status_code=401, body="nope")
        with self.assertRaises(GatewayError):
            SquareGateway(client, "LOC", "CAT").search_orders(START, END)


class PaidAtTests(SimpleTestCase):
    def test_paid_at_is_the_first_tenders_created_at(self) -> None:
        tenders = [mock.Mock(created_at="2026-09-29T15:11:16Z", payment_id="P1"),
                   mock.Mock(created_at="2026-09-29T15:20:00Z", payment_id="P2")]
        order = _order("O1", None, [_line()], tenders=tenders,
                       created_at="2026-09-29T15:09:40Z")
        self.assertEqual(_order_data(order).paid_at, datetime.datetime(
            2026, 9, 29, 15, 11, 16, tzinfo=datetime.timezone.utc))

    def test_paid_at_falls_back_to_the_orders_created_at(self) -> None:
        order = _order("O1", None, [_line()], tenders=None,
                       created_at="2026-09-29T15:09:40.5Z")
        paid_at = _order_data(order).paid_at
        self.assertEqual(paid_at, datetime.datetime(
            2026, 9, 29, 15, 9, 40, 500000, tzinfo=datetime.timezone.utc))
        self.assertIsNotNone(paid_at.tzinfo)

    def test_tender_without_created_at_falls_back_to_the_order(self) -> None:
        tenders = [mock.Mock(created_at=None, payment_id="P1")]
        order = _order("O1", None, [_line()], tenders=tenders,
                       created_at="2026-09-29T15:09:40Z")
        self.assertEqual(_order_data(order).paid_at, datetime.datetime(
            2026, 9, 29, 15, 9, 40, tzinfo=datetime.timezone.utc))

    def test_paid_at_is_none_without_tenders_or_created_at(self) -> None:
        order = _order("O1", None, [_line()], tenders=None, created_at=None)
        self.assertIsNone(_order_data(order).paid_at)

    def test_search_orders_also_fills_paid_at(self) -> None:
        client = mock.Mock()
        client.orders.search.return_value = mock.Mock(
            orders=[_order("O1", "2026-10-04T12:00:00Z", [_line()],
                           tenders=[mock.Mock(created_at="2026-10-01T12:00:00Z")])],
            cursor=None)
        [o] = SquareGateway(client, "LOC", "CAT").search_orders(START, END)
        self.assertEqual(o.paid_at, datetime.datetime(
            2026, 10, 1, 12, 0, tzinfo=datetime.timezone.utc))


class TenderTests(SimpleTestCase):
    def test_order_data_reads_tenders(self) -> None:
        order = _order("O1", None, [_line()], tenders=[_tender(
            "P1", card_details=mock.Mock(status="CAPTURED"), amount=1600)])
        self.assertEqual(_order_data(order).tenders,
                         (Tender("P1", "CAPTURED", "CARD", 1600),))

    def test_tender_without_card_details_has_blank_status(self) -> None:
        order = _order("O1", None, [_line()], tenders=[_tender("P1", amount=None)])
        self.assertEqual(_order_data(order).tenders, (Tender("P1", "", "CARD"),))

    def test_card_tender_is_paid_only_once_captured(self) -> None:
        self.assertTrue(Tender("P1", "CAPTURED", "CARD").paid)
        self.assertFalse(Tender("P1", "AUTHORIZED", "CARD").paid)
        self.assertFalse(Tender("P1", "", "CARD").paid)

    def test_wallet_tender_carries_no_status_and_is_paid(self) -> None:
        # Cash App Pay: Square records the tender with no details block, and
        # only once the money has moved.
        order = _order("O1", None, [_line()], tenders=[_tender(
            "P1", type="WALLET", amount=1600)])
        (tender,) = _order_data(order).tenders
        self.assertEqual(tender, Tender("P1", "", "WALLET", 1600))
        self.assertTrue(tender.paid)

    def test_afterpay_tender_reads_its_own_status(self) -> None:
        order = _order("O1", None, [_line()], tenders=[_tender(
            "P1", type="BUY_NOW_PAY_LATER",
            buy_now_pay_later_details=mock.Mock(status="CAPTURED"))])
        (tender,) = _order_data(order).tenders
        self.assertEqual(tender.status, "CAPTURED")
        self.assertTrue(tender.paid)
        self.assertFalse(Tender("P1", "AUTHORIZED", "BUY_NOW_PAY_LATER").paid)

    def test_bank_tender_is_paid_when_completed(self) -> None:
        order = _order("O1", None, [_line()], tenders=[_tender(
            "P1", type="BANK_ACCOUNT",
            bank_account_details=mock.Mock(status="COMPLETED"))])
        self.assertTrue(_order_data(order).tenders[0].paid)
        self.assertFalse(Tender("P1", "PENDING", "BANK_ACCOUNT").paid)

    def test_order_without_tenders_has_none(self) -> None:
        self.assertEqual(_order_data(_order("O1", None, [_line()])).tenders, ())


class GetGatewayTests(SimpleTestCase):
    def setUp(self) -> None:
        gateway_module.reset_client_cache()

    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_blank_token_returns_none(self) -> None:
        self.assertIsNone(get_gateway())

    def test_square_enabled_only_when_fully_configured(self) -> None:
        # The one answer to "is Square on?", for every page and panel.
        with override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                               SQUARE_TICKET_CATEGORY_ID="C"):
            self.assertTrue(square_enabled())
        with override_settings(SQUARE_ACCESS_TOKEN="", SQUARE_LOCATION_ID="L",
                               SQUARE_TICKET_CATEGORY_ID="C"):
            self.assertFalse(square_enabled())
        with override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="",
                               SQUARE_TICKET_CATEGORY_ID="C"):
            self.assertFalse(square_enabled())

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C", SQUARE_ENVIRONMENT="sandbox")
    def test_client_is_built_once_and_shared(self) -> None:
        # get_gateway() runs on page views; the client holds the connection
        # pool, so one per process, not one per call.
        with mock.patch("boxoffice.gateway.Square") as Square:
            first, second = get_gateway(), get_gateway()
        Square.assert_called_once()
        self.assertIs(first.client, second.client)
        with override_settings(SQUARE_ACCESS_TOKEN="other"), \
                mock.patch("boxoffice.gateway.Square") as Square:
            get_gateway()
        Square.assert_called_once_with(token="other",
                                       environment=SquareEnvironment.SANDBOX,
                                       timeout=10)

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C", SQUARE_ENVIRONMENT="sandbox")
    def test_token_builds_sandbox_gateway(self) -> None:
        with mock.patch("boxoffice.gateway.Square") as Square:
            gw = get_gateway()
        self.assertIsInstance(gw, SquareGateway)
        self.assertEqual(Square.call_args.kwargs["token"], "tok")
        self.assertEqual(Square.call_args.kwargs["timeout"], 10)
        self.assertEqual(Square.call_args.kwargs["environment"],
                         SquareEnvironment.SANDBOX)
        self.assertIs(gw.client, Square.return_value)
        self.assertEqual((gw.location_id, gw.category_id), ("L", "C"))

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="",
                       SQUARE_TICKET_CATEGORY_ID="C")
    def test_token_without_location_is_disabled_and_logged(self) -> None:
        with mock.patch("boxoffice.gateway.Square") as Square, \
                self.assertLogs("boxoffice.gateway", "ERROR") as logs:
            self.assertIsNone(get_gateway())
        Square.assert_not_called()
        self.assertIn("SQUARE_LOCATION_ID", logs.output[0])
        self.assertEqual(disabled_reason(), "SQUARE_LOCATION_ID is blank")

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="")
    def test_token_without_category_is_disabled_and_logged(self) -> None:
        with mock.patch("boxoffice.gateway.Square") as Square, \
                self.assertLogs("boxoffice.gateway", "ERROR") as logs:
            self.assertIsNone(get_gateway())
        Square.assert_not_called()
        self.assertIn("SQUARE_TICKET_CATEGORY_ID", logs.output[0])
        self.assertEqual(disabled_reason(), "SQUARE_TICKET_CATEGORY_ID is blank")

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="",
                       SQUARE_TICKET_CATEGORY_ID="")
    def test_both_ids_blank_are_both_named(self) -> None:
        self.assertEqual(
            disabled_reason(),
            "SQUARE_LOCATION_ID and SQUARE_TICKET_CATEGORY_ID are blank",
        )

    @override_settings(SQUARE_ACCESS_TOKEN="", SQUARE_LOCATION_ID="",
                       SQUARE_TICKET_CATEGORY_ID="")
    def test_blank_token_reason_does_not_log(self) -> None:
        self.assertEqual(disabled_reason(), "no SQUARE_ACCESS_TOKEN")
        with self.assertNoLogs("boxoffice.gateway"):
            self.assertIsNone(get_gateway())

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C")
    def test_fully_configured_has_no_reason(self) -> None:
        self.assertIsNone(disabled_reason())

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C", SQUARE_ENVIRONMENT="production")
    def test_production_setting_selects_production(self) -> None:
        with mock.patch("boxoffice.gateway.Square") as Square:
            get_gateway()
        self.assertEqual(Square.call_args.kwargs["environment"],
                         SquareEnvironment.PRODUCTION)

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C", SQUARE_ENVIRONMENT="Prod")
    def test_unknown_environment_is_disabled_and_logged(self) -> None:
        # A misspelt setting must not quietly pick the sandbox: with the
        # production token every call would be refused while Buy buttons show.
        with mock.patch("boxoffice.gateway.Square") as Square, \
                self.assertLogs("boxoffice.gateway", "ERROR") as logs:
            self.assertIsNone(get_gateway())
        Square.assert_not_called()
        self.assertEqual(disabled_reason(),
                         "SQUARE_ENVIRONMENT is 'Prod', not sandbox or production")
        self.assertIn("SQUARE_ENVIRONMENT", logs.output[0])


class ParseTimestampTests(SimpleTestCase):
    def test_square_z_timestamp_is_aware_utc(self) -> None:
        when = parse_timestamp("2026-10-03T03:12:00.000Z")
        self.assertEqual(when, datetime.datetime(2026, 10, 3, 3, 12,
                                                 tzinfo=datetime.timezone.utc))

    def test_blank_is_none(self) -> None:
        self.assertIsNone(parse_timestamp(None))
        self.assertIsNone(parse_timestamp(""))


class FakeGatewayTests(SimpleTestCase):
    def test_public_methods_match_the_real_gateway(self) -> None:
        public = [n for n in vars(SquareGateway) if not n.startswith("_")]
        self.assertEqual(len(public), 8)
        for name in public:
            self.assertEqual(inspect.signature(getattr(FakeGateway, name)),
                             inspect.signature(getattr(SquareGateway, name)), name)

    def test_both_gateways_implement_the_protocol(self) -> None:
        # Gateway is what callers are typed against; the fake and the real
        # one must both offer every method on it, with the same signature.
        protocol = [n for n in vars(Gateway)
                    if not n.startswith("_") and callable(getattr(Gateway, n))]
        self.assertEqual(len(protocol), 8)
        for name in protocol:
            for cls in (SquareGateway, FakeGateway):
                self.assertEqual(inspect.signature(getattr(cls, name)),
                                 inspect.signature(getattr(Gateway, name)),
                                 f"{cls.__name__}.{name}")

    def test_unknown_item_is_not_found(self) -> None:
        gw = FakeGateway()
        with self.assertRaises(NotFound):
            gw.retrieve_item("nope")
        with self.assertRaises(NotFound):
            gw.upload_item_image("nope", b"jpg", "Dune")

    def test_upload_item_image_mints_ids_and_delete_removes_them(self) -> None:
        gw = FakeGateway()
        result = gw.upsert_item(SPEC_FOR_7, item_id=None, version=None,
                                variation_ids_by_tier={})
        image_id = gw.upload_item_image(result.item_id, b"jpg", "Dune")
        self.assertEqual(image_id, "img-1")
        self.assertEqual(gw.images[image_id], (result.item_id, b"jpg"))
        gw.delete_item(image_id)
        self.assertNotIn(image_id, gw.images)
        with self.assertRaises(GatewayError):
            gw.upload_item_image("nope", b"jpg", "Dune")

    def test_fake_update_without_the_image_drops_it_like_square(self) -> None:
        gw = FakeGateway()
        created = gw.upsert_item(SPEC_FOR_7, item_id=None, version=None,
                                 variation_ids_by_tier={})
        image_id = gw.upload_item_image(created.item_id, b"jpg", "Dune")
        kept = gw.upsert_item(SPEC_FOR_7, item_id=created.item_id,
                              version=created.version,
                              variation_ids_by_tier=created.variation_ids_by_tier,
                              image_id=image_id)
        self.assertIn(image_id, gw.images)
        gw.upsert_item(SPEC_FOR_7, item_id=created.item_id, version=kept.version,
                       variation_ids_by_tier=created.variation_ids_by_tier)
        self.assertNotIn(image_id, gw.images)

    def test_create_mints_ids_and_update_bumps_version(self) -> None:
        gw = FakeGateway()
        created = gw.upsert_item(SPEC_FOR_7, item_id=None, version=None,
                                 variation_ids_by_tier={})
        self.assertEqual(created.item_id, "item-1")
        self.assertEqual(created.version, 1)
        self.assertEqual(list(created.variation_ids_by_tier.values()),
                         [f"var-{n}" for n in range(1, 6)])
        self.assertEqual(gw.items["item-1"].variation_ids_by_sku["fkc-eng-7-adult"],
                         "var-1")
        gw.items["item-1"] = dataclasses.replace(gw.items["item-1"], version=99)
        updated = gw.upsert_item(SPEC_FOR_7, item_id="item-1", version=99,
                                 variation_ids_by_tier=created.variation_ids_by_tier)
        self.assertEqual(updated, UpsertResult("item-1", 100,
                                               created.variation_ids_by_tier))
        self.assertEqual(gw.calls[-1][0], "upsert_item")
        self.assertEqual(gw.calls[-1][1]["version"], 99)

    def test_stale_version_raises_mismatch(self) -> None:
        gw = FakeGateway()
        gw.upsert_item(SPEC_FOR_7, item_id=None, version=None, variation_ids_by_tier={})
        with self.assertRaises(VersionMismatch):
            gw.upsert_item(SPEC_FOR_7, item_id="item-1", version=7,
                           variation_ids_by_tier={})
        self.assertEqual(gw.items["item-1"].version, 1)

    def test_fail_with_raises_from_every_method_without_minting(self) -> None:
        gw = FakeGateway(fail_with=GatewayError("down"))
        for call in [
            lambda: gw.upsert_item(SPEC_FOR_7, item_id=None, version=None,
                                   variation_ids_by_tier={}),
            lambda: gw.delete_item("x"), lambda: gw.retrieve_item("x"),
            lambda: gw.search_orders(START, END), lambda: gw.list_ticket_items(),
            lambda: gw.lookup_categories(["v"]),
            lambda: gw.search_open_orders(START, END),
        ]:
            with self.assertRaisesMessage(GatewayError, "down"):
                call()
        self.assertEqual(len(gw.calls), 7)
        gw.fail_with = None
        self.assertEqual(gw.upsert_item(SPEC_FOR_7, item_id=None, version=None,
                                        variation_ids_by_tier={}).item_id, "item-1")

    def test_delete_unknown_succeeds_and_delete_known_removes(self) -> None:
        gw = FakeGateway()
        gw.delete_item("nope")  # Square's batch_delete does not raise either.
        self.assertEqual(gw.calls, [("delete_item", {"item_id": "nope"})])
        gw.upsert_item(SPEC_FOR_7, item_id=None, version=None, variation_ids_by_tier={})
        gw.delete_item("item-1")
        self.assertEqual(gw.items, {})
        self.assertEqual(gw.list_ticket_items(), [])

    def test_search_orders_is_half_open(self) -> None:
        gw = FakeGateway()
        gw.orders = [OrderData(o, at, ()) for o, at in
                     [("before", START - datetime.timedelta(seconds=1)),
                      ("start", START), ("end", END)]]
        self.assertEqual([o.order_id for o in gw.search_orders(START, END)], ["start"])

    def test_lookup_categories_returns_known_ids_only(self) -> None:
        gw = FakeGateway()
        gw.categories = {"V1": "CAT", "V2": "POP"}
        self.assertEqual(gw.lookup_categories(["V1", "V3"]), {"V1": "CAT"})

    @staticmethod
    def open_order(gw: FakeGateway, order_id: str) -> None:
        """An unpaid website order: OPEN in Square, so no closed_at."""
        gw.orders.append(OrderData(order_id, None, (
            OrderLine(f"{order_id}-0", "Dune", "Adult", "var-adult", 2, 1600),)))

    def test_fake_search_open_orders_returns_open_orders_touched_in_window(self):
        # Like Square's updated_at filter: an unpaid order is "touched" when
        # made, a paid one when paid; a closed order is no longer open.
        gw = FakeGateway()
        for order_id in ("SQ-1", "SQ-2", "SQ-3"):
            self.open_order(gw, order_id)
        gw.pay("SQ-2", paid_at=START)
        gw.pay("SQ-3", paid_at=END)
        gw.orders.append(OrderData("closed", START, ()))
        self.assertEqual([o.order_id for o in gw.search_open_orders(START, END)],
                         ["SQ-1", "SQ-2"])
        self.assertEqual(gw.calls[-1],
                         ("search_open_orders", {"start": START, "end": END}))
        self.assertEqual(gw.search_orders(START, END)[0].order_id, "closed")

    def test_fake_pay_marks_tender_captured(self) -> None:
        gw = FakeGateway()
        self.open_order(gw, "SQ-1")
        gw.pay("SQ-1", "P7")
        [paid] = gw.orders
        # The tender covers the order: the sum of its lines.
        self.assertEqual(paid.tenders, (Tender("P7", "CAPTURED", "CARD", 1600),))
        self.assertIsNotNone(paid.paid_at.tzinfo)

    def test_fake_pay_can_use_a_wallet_or_pay_short(self) -> None:
        gw = FakeGateway()
        self.open_order(gw, "SQ-1")
        gw.pay("SQ-1", "P8", tender_type="WALLET", amount_cents=100)
        self.assertEqual(gw.orders[0].tenders, (Tender("P8", "", "WALLET", 100),))
        self.assertEqual(len(gw.orders), 1)

    def test_fake_pay_unknown_order_is_not_found(self) -> None:
        with self.assertRaises(NotFound):
            FakeGateway().pay("nope")
