import uuid

from square_integration.services.square_client import get_square_client, idempotency_key
from square_integration.models import CatalogCategory, CatalogObject, CatalogObjectType, CatalogItemData, CategoryData, CategoryParent, CatalogRequest


def build_categories_list():
    client = get_square_client()
    for category in CatalogCategory.objects.filter(active=True):

        category_request_object = CatalogObject(
                type=CatalogObjectType.CATEGORY,
                id=category.square_id or f"#cat_{uuid.uuid4()}",
                category_data=CategoryData(
                    name=category.name,
                    is_top_level=category.parent is None,
                    parent_category=(
                        None if category.parent is None else
                        CategoryParent(id=category.parent.square_id)
                    )
                )
            )

        if category.square_id:
            current_object_response = client.catalog.object.get(object_id=category.square_id)
            category_request_object.version = current_object_response.object.version

        response = client.catalog.object.upsert(idempotency_key=idempotency_key(prefix="cats"),
                                                object=category_request_object)
        category.square_id = response.catalog_object.id
        category.save()
