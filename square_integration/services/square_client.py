# square_integration/services/square_client.py

from collections.abc import Callable
from typing import Any

import uuid
from square import Square
from square.environment import SquareEnvironment
from django.conf import settings


def get_square_client() -> Square:
    square_environment = (
        SquareEnvironment.PRODUCTION
        if settings.SQUARE_ENVIRONMENT == "production"
        else SquareEnvironment.SANDBOX
    )
    return Square(environment=square_environment, token=settings.SQUARE_ACCESS_TOKEN)


def idempotency_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def upsert_catalog_object_for_instance(
    *,
    instance: Any,
    square_id_attr: str,
    build_request_object: Callable[[Any], Any],
    apply_version_from_remote: Callable[[Any, Any], None] | None = None,
    after_upsert: Callable[[Any, Any], None],
    idempotency_prefix: str,
) -> None:
    """
    Shared helper for syncing a Django model instance to Square's Catalog.

    - `square_id_attr`: name of the field on `instance` that holds the Square object id
      (e.g. "square_item_id" or "square_id").
    - `build_request_object`: builds and returns a CatalogObject to send.
    - `apply_version_from_remote`: given (request_object, remote_object) can copy .version
      and other bits from Square to the request.
    - `after_upsert`: given (instance, response_object) updates local fields and saves.
    """
    client = get_square_client()

    request_object = build_request_object(instance)
    square_id = getattr(instance, square_id_attr, None)

    if square_id:
        current_object_response = client.catalog.object.get(object_id=square_id)
        remote_object = current_object_response.object

        if apply_version_from_remote is not None:
            apply_version_from_remote(request_object, remote_object)

    response = client.catalog.object.upsert(
        idempotency_key=idempotency_key(prefix=f"{idempotency_prefix}-{instance.pk}"),
        object=request_object,
    )

    after_upsert(instance, response.catalog_object)
