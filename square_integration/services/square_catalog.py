import logging
from typing import Any, Iterable, Tuple

from square.core.api_error import ApiError

from square_integration.square_client import get_square_client, idempotency_key
from square_integration.models import Category

logger = logging.getLogger(__name__)


# ============================
# Internal helpers
# ============================


def _parse_upsert_response(resp: Any) -> Tuple[Any, Iterable[Any]]:
    """
    Normalize Square upsert response into (catalog_object, id_mappings).

    Supports:
      - New SDK Pydantic models with .catalog_object / .id_mappings
      - ApiResponse-style objects with .body
      - Plain dicts (tests/mocks)
    """
    # Direct model-style
    if hasattr(resp, "catalog_object") or hasattr(resp, "id_mappings"):
        return getattr(resp, "catalog_object", None), getattr(resp, "id_mappings", None) or []

    body = getattr(resp, "body", None)

    if body is None:
        if isinstance(resp, dict):
            return resp.get("catalog_object"), resp.get("id_mappings") or []
        return None, []

    if isinstance(body, dict):
        return body.get("catalog_object"), body.get("id_mappings") or []

    if hasattr(body, "catalog_object") or hasattr(body, "id_mappings"):
        return getattr(body, "catalog_object", None), getattr(body, "id_mappings", None) or []

    if isinstance(resp, dict):
        return resp.get("catalog_object"), resp.get("id_mappings") or []

    return None, []


def _get_attr_or_key(obj: Any, key: str):
    """Safely read `obj.key` or `obj[key]`."""
    if obj is None:
        return None
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key)
    return None


# ============================
# Core sync
# ============================


def sync_categories_to_square() -> None:
    """
    Sync Django Category -> Square Catalog CATEGORY.

    Rules:
      - For each active Category:
          - If no square_id:
                create a CATEGORY in Square
                store returned id in category.square_id
          - If square_id exists:
                ensure name is updated in Square (with version handling)

    This is idempotent and safe for cron/management commands.
    """
    client = get_square_client()

    # Use only active categories; adjust if you want all.
    categories = Category.objects.filter(active=True)

    for category in categories:
        if category.square_id:
            _sync_existing_square_category(client, category)
        else:
            _create_square_category(client, category)


# ============================
# Create path
# ============================


def _create_square_category(client, category: Category) -> None:
    """
    Create a Square CATEGORY for a Category without square_id.
    """
    client_object_id = f"#category-{category.id}"

    try:
        resp = client.catalog.object.upsert(
            idempotency_key=idempotency_key(f"category-create-{category.id}"),
            object={
                "type": "CATEGORY",
                "id": client_object_id,  # temporary client ID
                "category_data": {
                    "name": category.name,
                },
            },
        )
    except ApiError as e:
        logger.error(
            "Square ApiError creating CATEGORY for Category %s: %s",
            category.id,
            getattr(e, "body", e),
        )
        return
    except Exception:
        logger.exception(
            "Unexpected error creating CATEGORY for Category %s",
            category.id,
        )
        return

    catalog_object, id_mappings = _parse_upsert_response(resp)

    # Try to resolve the real id via id_mappings first
    real_id = None
    for m in id_mappings or []:
        client_id = _get_attr_or_key(m, "client_object_id")
        obj_id = _get_attr_or_key(m, "object_id")
        if client_id == client_object_id and obj_id:
            real_id = obj_id
            break

    # Fallback: read from catalog_object
    if not real_id:
        real_id = _get_attr_or_key(catalog_object, "id")

    if not real_id:
        logger.error(
            "Could not resolve Square CATEGORY id for Category %s after upsert.",
            category.id,
        )
        return

    category.square_id = real_id
    category.save(update_fields=["square_id"])
    logger.info(
        "Synced Category %s (%s) to Square CATEGORY %s",
        category.id,
        category.name,
        category.square_id,
    )


# ============================
# Update path
# ============================


def _sync_existing_square_category(client, category: Category) -> None:
    """
    Ensure the existing Square CATEGORY's name matches the local Category.

    Uses retrieve + upsert with version to avoid VERSION_MISMATCH.
    """
    square_id = category.square_id

    # 1) Retrieve latest version from Square
    try:
        resp = client.catalog.retrieve_catalog_object(object_id=square_id)
    except ApiError as e:
        body = getattr(e, "body", {}) or {}
        code = None
        if isinstance(body, dict):
            errs = body.get("errors") or []
            if errs:
                code = errs[0].get("code")
        # If not found, try recreating on next run by clearing square_id
        if code == "NOT_FOUND":
            logger.warning(
                "Square CATEGORY %s for Category %s not found; clearing square_id.",
                square_id,
                category.id,
            )
            category.square_id = None
            category.save(update_fields=["square_id"])
        else:
            logger.error(
                "Square ApiError retrieving CATEGORY %s for Category %s: %s",
                square_id,
                category.id,
                body or e,
            )
        return
    except Exception:
        logger.exception(
            "Unexpected error retrieving CATEGORY %s for Category %s",
            square_id,
            category.id,
        )
        return

    catalog_object = _get_attr_or_key(resp, "object") or _get_attr_or_key(resp, "catalog_object")
    if not catalog_object:
        logger.error(
            "No catalog_object when retrieving CATEGORY %s for Category %s",
            square_id,
            category.id,
        )
        return

    current_name = _get_attr_or_key(_get_attr_or_key(catalog_object, "category_data"), "name")
    version = _get_attr_or_key(catalog_object, "version")

    # If name is already correct, nothing to do
    if current_name == category.name:
        return

    # 2) Upsert with latest version + new name
    payload = {
        "type": "CATEGORY",
        "id": square_id,
        "category_data": {
            "name": category.name,
        },
    }
    if version is not None:
        payload["version"] = version

    try:
        client.catalog.object.upsert(
            idempotency_key=idempotency_key(f"category-update-{category.id}-{version}"),
            object=payload,
        )
    except ApiError as e:
        logger.error(
            "Square ApiError updating CATEGORY %s for Category %s: %s",
            square_id,
            category.id,
            getattr(e, "body", e),
        )
        return
    except Exception:
        logger.exception(
            "Unexpected error updating CATEGORY %s for Category %s",
            square_id,
            category.id,
        )
        return

    logger.info(
        "Updated Square CATEGORY %s name to '%s' for Category %s",
        square_id,
        category.name,
        category.id,
    )
