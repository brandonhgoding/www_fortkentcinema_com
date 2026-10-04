import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from twilio.request_validator import RequestValidator

logger = logging.getLogger(__name__)

View = Callable[..., HttpResponse]


def _signed_url(request: HttpRequest) -> str:
    """The URL Twilio computed its signature over: the public one it called,
    query string included.

    Behind nginx, build_absolute_uri() is only right because USE_PROXY_HEADERS
    turns on SECURE_PROXY_SSL_HEADER and USE_X_FORWARDED_HOST; without them it
    yields http://<internal>/... and every signature fails.
    TWILIO_WEBHOOK_BASE_URL pins the scheme and host instead.
    """
    base = settings.TWILIO_WEBHOOK_BASE_URL
    if base:
        return base.rstrip("/") + request.get_full_path()
    return request.build_absolute_uri()


def twilio_webhook(view: View) -> View:
    """POST-only, CSRF-exempt, and 403 unless X-Twilio-Signature checks out.

    CSRF can't apply — Twilio has no token to send — so the signature is what
    proves a request came from Twilio. Every phone webhook must use this.
    """

    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        token = settings.TWILIO_AUTH_TOKEN
        if not token:
            logger.error("TWILIO_AUTH_TOKEN is not set; rejecting Twilio webhook.")
            return HttpResponseForbidden()

        url = _signed_url(request)
        signature = request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
        if not RequestValidator(token).validate(url, request.POST, signature):
            logger.warning("Rejected Twilio webhook with a bad signature for %s", url)
            return HttpResponseForbidden()

        return view(request, *args, **kwargs)

    return csrf_exempt(require_POST(wrapped))
