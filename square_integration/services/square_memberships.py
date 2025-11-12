from square_integration.services.square_client import get_square_client, idempotency_key
from memberships.models import MembershipType


def build_categories_list():
    client = get_square_client()

    for membership in MembershipType.objects.filter(active=True):
        membership_object = {
            "type": "ITEM",
            "id": membership.square_id or "#membership_object",
            "present_at_all_locations": True,
            "item_data": {
                "name": membership.name,
                "description": membership.description,
                "variations": [
                    {
                        "type": "ITEM_VARIATION",
                        "id": membership.square_item_variation_id or "#membership_variation",
                        "item_variation_data": {
                            "name": f"{membership.duration_months}-Month Membership",
                            "pricing_type": "FIXED_PRICING",
                            "price_money": {
                                "amount": membership.price_cents,
                                "currency": membership.currency
                            }
                        }
                    }
                ]
            }
        }

        if membership.square_id:
            current_object_response = client.catalog.object.get(object_id=membership.square_id)
            membership_object["version"] = current_object_response.object.version

        response = client.catalog.object.upsert(
            idempotency_key=idempotency_key(prefix="cats"),
            object=membership_object
        )
        membership.square_id = response.catalog_object.id
        membership.square_item_variation_id = response.catalog_object.item_data.variations[0].id
        membership.save()
