import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from square.utils.webhooks_helper import verify_signature

logger = logging.getLogger(__name__)

View = Callable[..., HttpResponse]


def square_webhook(view: View) -> View:
    """POST-only, CSRF-exempt, and 403 unless X-Square-HmacSha256-Signature
    checks out.

    CSRF can't apply — Square has no token to send — so the signature is what
    proves a request came from Square. Square signs the registered
    notification URL plus the raw body, so SQUARE_WEBHOOK_URL must match what
    is registered in the Square dashboard, not whatever host Django sees.
    """

    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        key = settings.SQUARE_WEBHOOK_SIGNATURE_KEY
        url = settings.SQUARE_WEBHOOK_URL
        if not key or not url:
            logger.error("SQUARE_WEBHOOK_SIGNATURE_KEY or SQUARE_WEBHOOK_URL is "
                         "not set; rejecting Square webhook.")
            return HttpResponseForbidden()

        if not verify_signature(
            request_body=request.body.decode("utf-8", errors="replace"),
            signature_header=request.META.get("HTTP_X_SQUARE_HMACSHA256_SIGNATURE", ""),
            signature_key=key,
            notification_url=url,
        ):
            logger.warning("Rejected Square webhook with a bad signature.")
            return HttpResponseForbidden()

        return view(request, *args, **kwargs)

    return csrf_exempt(require_POST(wrapped))
