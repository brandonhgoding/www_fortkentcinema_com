import logging
from decimal import Decimal

from square.core.api_error import ApiError

from cinema.square_client import get_square_client, idempotency_key
from cinema.models import Booking
from cinema.pricing import get_rate_for_screening

logger = logging.getLogger(__name__)

CURRENCY = "USD"


def _parse_upsert_response(resp):
    """
    Normalize Square upsert response into (catalog_object, id_mappings).

    Handles:
      - New SDK Pydantic models (e.g. UpsertCatalogObjectResponse)
      - ApiResponse with .body as dict or model
      - Plain dict (e.g. in tests)
    """
    # Case 1: New SDK: direct Pydantic response with attributes
    if hasattr(resp, "catalog_object") or hasattr(resp, "id_mappings"):
        catalog_object = getattr(resp, "catalog_object", None)
        id_mappings = getattr(resp, "id_mappings", None) or []
        return catalog_object, id_mappings

    # Case 2: ApiResponse style with .body
    body = getattr(resp, "body", None)

    if body is None:
        return None, []

    # body is a dict
    if isinstance(body, dict):
        return body.get("catalog_object"), body.get("id_mappings") or []

    # body is a Pydantic model-like with attrs
    if hasattr(body, "catalog_object") or hasattr(body, "id_mappings"):
        catalog_object = getattr(body, "catalog_object", None)
        id_mappings = getattr(body, "id_mappings", None) or []
        return catalog_object, id_mappings

    # Case 3: plain dict response
    if isinstance(resp, dict):
        return resp.get("catalog_object"), resp.get("id_mappings") or []

    return None, []


def _format_variation_name(screening_time):
    """
    Human-friendly variation name for a showtime.
    Example: 'Nov 21 • 7:30 PM (Evening)'.
    Adjust labeling logic if you have a real matinee flag/field.
    """
    date_str = screening_time.date.strftime("%b %d")
    time_str = screening_time.time.strftime("%I:%M %p").lstrip("0")

    # If your model has something better than is_matinee, swap this.
    label = getattr(screening_time, "label", None)
    if not label:
        label = "Matinee" if getattr(screening_time, "is_matinee", False) else "Evening"

    return f"{date_str} • {time_str} ({label})"


def sync_bookings_and_showtimes_to_square():
    """
    Booking -> Square ITEM
      - name: booking.film.title
      - description: booking.film.description
      - stored in booking.square_item_id

    ScreeningTime -> Square ITEM_VARIATION under that ITEM
      - name: formatted date/time
      - price: from get_rate_for_screening(screening_time)
      - stored in screening_time.square_variation_id

    Idempotent: safe to run via cron or manually.
    """
    client = get_square_client()

    # If you have flags like active/upcoming, filter here.
    bookings = (
        Booking.objects
        .select_related("film")
        .prefetch_related("screening_times")
        .all()
    )

    for booking in bookings:
        film = booking.film
        if not film:
            continue

        screening_times = list(booking.screening_times.all())
        if not screening_times:
            continue

        # ---------- 1) Ensure ITEM for this booking ----------
        if not booking.square_item_id:
            variations_payload = []

            for st in screening_times:
                rate = get_rate_for_screening(st)
                if not rate:
                    logger.warning(
                        "No rate resolved for ScreeningTime %s on Booking %s; skipping",
                        st.id,
                        booking.id,
                    )
                    continue

                client_var_id = f"#booking-{booking.id}-st-{st.id}"

                variations_payload.append(
                    {
                        "type": "ITEM_VARIATION",
                        "id": client_var_id,
                        "present_at_all_locations": True,
                        "item_variation_data": {
                            "name": _format_variation_name(st),
                            "pricing_type": "FIXED_PRICING",
                            "price_money": {
                                "amount": int(Decimal(rate.price) * 100),
                                "currency": CURRENCY,
                            },
                        },
                    }
                )

            if not variations_payload:
                # No valid showtimes with rates; nothing to sync for this booking.
                continue

            try:
                resp = client.catalog.object.upsert(
                    idempotency_key=idempotency_key(f"booking-{booking.id}"),
                    object={
                        "type": "ITEM",
                        "id": f"#booking-{booking.id}",  # client temp id
                        "present_at_all_locations": True,
                        "item_data": {
                            "name": film.title,
                            "description": getattr(film, "description", "") or "",
                            "variations": variations_payload,
                        },
                    },
                )
            except ApiError as e:
                logger.error(
                    "Square ApiError creating ITEM for Booking %s: %s",
                    booking.id,
                    getattr(e, "body", e),
                )
                continue
            except Exception:
                logger.exception(
                    "Unexpected error creating ITEM for Booking %s",
                    booking.id,
                )
                continue

            catalog_object, id_mappings = _parse_upsert_response(resp)

            if not catalog_object:
                logger.error(
                    "No catalog_object in ITEM upsert response for Booking %s",
                    booking.id,
                )
                continue

            # catalog_object may be dict-like or model-like
            item_id = getattr(catalog_object, "id", None) or (
                isinstance(catalog_object, dict) and catalog_object.get("id")
            )
            if not item_id:
                logger.error(
                    "Missing ITEM id in upsert response for Booking %s",
                    booking.id,
                )
                continue

            booking.square_item_id = item_id
            booking.save(update_fields=["square_item_id"])

            # Resolve variation IDs from id_mappings
            mapping = {}
            for m in id_mappings:
                client_id = getattr(m, "client_object_id", None) or (
                    isinstance(m, dict) and m.get("client_object_id")
                )
                obj_id = getattr(m, "object_id", None) or (
                    isinstance(m, dict) and m.get("object_id")
                )
                if client_id and obj_id:
                    mapping[client_id] = obj_id

            for st in screening_times:
                client_id = f"#booking-{booking.id}-st-{st.id}"
                real_var_id = mapping.get(client_id)
                if real_var_id and st.square_variation_id != real_var_id:
                    st.square_variation_id = real_var_id
                    st.save(update_fields=["square_variation_id"])

        else:
            # ---------- 2) ITEM exists: upsert/refresh each showtime variation ----------
            item_id = booking.square_item_id

            for st in screening_times:
                rate = get_rate_for_screening(st)
                if not rate:
                    logger.warning(
                        "No rate resolved for ScreeningTime %s on Booking %s; skipping",
                        st.id,
                        booking.id,
                    )
                    continue

                name = _format_variation_name(st)
                # Use existing var id if known; otherwise a stable client temp ID
                candidate_id = (
                    st.square_variation_id
                    or f"#booking-{booking.id}-st-{st.id}"
                )

                try:
                    resp = client.catalog.object.upsert(
                        idempotency_key=idempotency_key(
                            f"booking-{booking.id}-st-{st.id}"
                        ),
                        object={
                            "type": "ITEM_VARIATION",
                            "id": candidate_id,
                            "present_at_all_locations": True,
                            "item_variation_data": {
                                "item_id": item_id,
                                "name": name,
                                "pricing_type": "FIXED_PRICING",
                                "price_money": {
                                    "amount": int(Decimal(rate.price) * 100),
                                    "currency": CURRENCY,
                                },
                            },
                        },
                    )
                except ApiError as e:
                    logger.error(
                        "Square ApiError upserting VARIATION for Booking %s / ST %s: %s",
                        booking.id,
                        st.id,
                        getattr(e, "body", e),
                    )
                    continue
                except Exception:
                    logger.exception(
                        "Unexpected error upserting VARIATION for Booking %s / ST %s",
                        booking.id,
                        st.id,
                    )
                    continue

                catalog_object, _ = _parse_upsert_response(resp)
                if not catalog_object:
                    logger.error(
                        "No catalog_object in VARIATION upsert for Booking %s / ST %s",
                        booking.id,
                        st.id,
                    )
                    continue

                real_id = getattr(catalog_object, "id", None) or (
                    isinstance(catalog_object, dict)
                    and catalog_object.get("id")
                )
                if real_id and real_id != st.square_variation_id:
                    st.square_variation_id = real_id
                    st.save(update_fields=["square_variation_id"])
