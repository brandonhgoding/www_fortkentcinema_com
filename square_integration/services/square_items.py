import uuid

from square_integration.models import (
    CatalogObject,
    CatalogObjectType,
    CatalogItemVariation,
    CatalogItemVariationData,
    CatalogPriceMoney,
    CatalogItemData, ItemCategoryData,
)
from square_integration.services.square_client import get_square_client, idempotency_key
from inventory.models import InventoryItem


def build_square_catalog_items():
    client = get_square_client()

    for item in InventoryItem.objects.filter(active=True, parent_item__isnull=True):
        item_id = item.square_item_id or f"#item_{uuid.uuid4()}"

        variation_objects = []

        for variation in item.get_self_and_active_variations():
            variation_id = variation.square_item_variation_id or f"#itemvar_{uuid.uuid4()}"
            variation_data = CatalogItemVariation(
                type=CatalogObjectType.ITEM_VARIATION,
                id=variation_id,
                item_variation_data=CatalogItemVariationData(
                    name=variation.name,
                    price_money=CatalogPriceMoney(
                        amount=variation.price_cents,
                        currency=variation.currency,
                    ),
                    item_id=item_id,
                    pricing_type="FIXED_PRICING",
                    is_taxable=variation.is_taxable,
                    tax_ids=[variation.tax_rate.square_id if variation.tax_rate else None],
                ),
            )
            if variation.square_item_variation_id:
                variation_request = client.catalog.object.get(object_id=variation.square_item_variation_id)
                variation_data.version = variation_request.object.version
            variation_objects.append(variation_data)

        inventory_item = CatalogObject(
            type=CatalogObjectType.ITEM,
            id=item_id,
            item_data=CatalogItemData(
                name=item.name,
                description=item.description,
                variations=variation_objects,
                is_taxable=item.is_taxable,
                tax_ids=[item.tax_rate.square_id if item.tax_rate else None],
                categories=[ItemCategoryData(id=str(item.category.square_id))] if item.category else [],
            ),
        )

        if item.square_item_id:
            current_object_response = client.catalog.object.get(object_id=item.square_item_id)
            inventory_item.version = current_object_response.object.version

        response = client.catalog.object.upsert(
            idempotency_key=idempotency_key(prefix=f"item-{uuid.uuid4()}"),
            object=inventory_item,
        )

        item.square_item_id = response.catalog_object.id
        item.save()
        for variation in response.catalog_object.item_data.variations:
            inv_variation = item.variations.filter(name=variation.item_variation_data.name).first()
            if inv_variation:
                inv_variation.square_item_variation_id = variation.id
                inv_variation.square_variation_version = variation.version
                inv_variation.save()

