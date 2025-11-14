import uuid

from square_integration.models import CatalogObject, CatalogObjectType, CatalogItemVariation, CatalogItemVariationData, \
    CatalogPriceMoney, CatalogItemData
from square_integration.services.square_client import get_square_client, idempotency_key
from memberships.models import MembershipType


def build_membership_catalog_items():
    client = get_square_client()

    for membership in MembershipType.objects.filter(active=True):
        item_id = membership.square_item_id or f"#mem_{uuid.uuid4()}"
        variation_id = membership.square_item_variation_id or f"#memvar_{uuid.uuid4()}"

        variation_object = CatalogItemVariation(
            type=CatalogObjectType.ITEM_VARIATION,   # this becomes variations[0].type
            id=variation_id,
            item_variation_data=CatalogItemVariationData(
                name="Regular",
                price_money=CatalogPriceMoney(
                    amount=membership.price_cents,
                    currency=membership.currency,
                ),
                item_id=item_id,
                pricing_type="FIXED_PRICING",
            ),
        )

        membership_request_object = CatalogObject(
            type=CatalogObjectType.ITEM,
            id=item_id,
            item_data=CatalogItemData(
                name=membership.name,
                description=membership.description,
                variations=[variation_object],
            ),
        )

        if membership.square_item_id:
            # NOTE: this probably wants square_item_id, not square_id
            current_object_response = client.catalog.object.get(
                object_id=membership.square_item_id
            )
            membership_request_object.version = current_object_response.object.version
            variation_object.version = current_object_response.object.item_data.variations[0].version
        response = client.catalog.object.upsert(
            idempotency_key=idempotency_key(prefix=f"mems-{membership.pk}"),
            object=membership_request_object,
        )

        membership.square_item_id = response.catalog_object.id
        membership.square_item_variation_id = (
            response.catalog_object.item_data.variations[0].id
        )
        membership.save()
