from square_integration.services.square_client import get_square_client, idempotency_key
from square_integration.models import Category


def build_categories_list():
    client = get_square_client()

    for category in Category.objects.filter(active=True):
        category_object = {
            "type": "CATEGORY",
            "id": category.square_id or "#catalog_object",
            "present_at_all_locations": True,
            "category_data": {
                "name": category.name,
                "is_top_level": True,
                "description": category.description
            }
        }
        if category.square_id:
            current_object_response = client.catalog.object.get(object_id=category.square_id)
            category_object["version"] = current_object_response.object.version

        response = client.catalog.object.upsert(
            idempotency_key=idempotency_key(prefix="cats"),
            object=category_object
        )
        category.square_id = response.catalog_object.id
        category.save()
