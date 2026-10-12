"""The mailing-list signup: a form, and the confirmation email it sends.

Double opt-in. Submitting the form never puts an address on the list; it
stores it PENDING and emails a link, and only following that link joins it
(see Subscriber.confirm). That keeps one person from signing up another.
"""

import logging
import time
from datetime import datetime, timezone as dt_timezone

from django import forms
from django.core import signing
from django.core.mail import EmailMessage
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from audience.models import Subscriber
from cinema.voting import client_ip
from web.constants import SITE_CONFIG

logger = logging.getLogger(__name__)

# Where on the site the form was submitted from. Free text from the client,
# so anything unlisted is stored as "site" rather than trusted.
SOURCES = frozenset({"home_showtimes", "home_empty", "movie_page"})

_CONFIRM_SALT = "list-confirm"
_CONFIRM_MAX_AGE = 7 * 24 * 60 * 60

SUBJECT = "Confirm your Fort Kent Cinema emails"
ERROR = "That doesn't look like an email address."


def source_for(location: str) -> str:
    return location if location in SOURCES else "site"


def confirm_token(subscriber: Subscriber) -> str:
    # The issue time is a float, not whole seconds: Task 3 compares it with
    # the moment of an unsubscribe, and truncating would make a link issued
    # just after an opt-out look older than it.
    return signing.dumps({"pk": subscriber.pk, "at": time.time()}, salt=_CONFIRM_SALT)


def load_confirm_token(token: str) -> tuple[Subscriber, datetime] | None:
    """The subscriber and issue time a token names, or None if unusable."""
    try:
        data = signing.loads(token, salt=_CONFIRM_SALT, max_age=_CONFIRM_MAX_AGE)
        pk, issued = data["pk"], data["at"]
        issued_at = datetime.fromtimestamp(issued, tz=dt_timezone.utc)
    except (signing.BadSignature, KeyError, TypeError, ValueError, OverflowError):
        return None
    subscriber = Subscriber.objects.filter(pk=pk).first()
    if subscriber is None:
        return None
    return subscriber, issued_at


def _body(request, subscriber: Subscriber) -> str:
    cinema = SITE_CONFIG["cinema"]
    link = request.build_absolute_uri(
        reverse("list_confirm", args=[confirm_token(subscriber)])
    )
    return (
        "Click below to confirm you'd like the weekend's showtimes from "
        "Fort Kent Cinema by email every Thursday. The first one is on its "
        "way soon.\n\n"
        f"{link}\n\n"
        "Didn't ask for this? Ignore this email and you won't hear from us.\n\n"
        f"Fort Kent Cinema · {cinema['address']['street']} · {cinema['phone']}\n"
    )


def send_confirmation(request, subscriber: Subscriber) -> bool:
    """Email the confirm link; True if it went out."""
    now = timezone.now()
    previous = subscriber.confirmation_sent_at
    # Claim the send before making it. request_signup only read the send
    # time, so two simultaneous submits both pass it; only one of them can
    # win this conditional update, and the loser sends nothing.
    claimed = (
        Subscriber.objects.filter(pk=subscriber.pk)
        .filter(
            Q(confirmation_sent_at__isnull=True)
            | Q(confirmation_sent_at__lte=now - Subscriber.CONFIRMATION_RESEND_AFTER)
        )
        .update(confirmation_sent_at=now)
    )
    if claimed != 1:
        return False
    try:
        EmailMessage(SUBJECT, _body(request, subscriber), to=[subscriber.email]).send()
    except Exception:
        logger.exception(
            "Could not send list confirmation to subscriber %s", subscriber.pk
        )
        # Give the claim back so the very next submit tries again.
        Subscriber.objects.filter(pk=subscriber.pk).update(
            confirmation_sent_at=previous
        )
        return False
    return True


def start_signup(request, email: str, source: str) -> None:
    subscriber = Subscriber.objects.request_signup(
        email, source=source, ip=client_ip(request)
    )
    if subscriber is not None:
        send_confirmation(request, subscriber)


class _SignupForm(forms.Form):
    email = forms.EmailField(max_length=Subscriber.EMAIL_MAX_LENGTH)
    # Honeypot: hidden from people, filled in by form-stuffing bots.
    website = forms.CharField(required=False)


class ListSignupView(View):
    """POST /subscribe: the same reply whether or not we sent anything.

    Telling "already on the list" apart from "new" would let anyone probe
    who is subscribed, so every valid submit gets the same "check your inbox".
    """

    http_method_names = ["post", "options"]

    def post(self, request):
        location = request.POST.get("location", "")
        ctx = {"list_signup_location": location}
        form = _SignupForm(request.POST)
        if not form.is_valid():
            ctx["list_signup_error"] = ERROR
            ctx["list_signup_email"] = request.POST.get("email", "")
        else:
            ctx["list_signup_done"] = True
            if not form.cleaned_data["website"]:
                start_signup(request, form.cleaned_data["email"], source_for(location))
        if request.headers.get("HX-Request"):
            return render(request, "partials/list_signup.html", ctx)
        referer = request.headers.get("Referer", "")
        ctx["back_url"] = (
            referer
            if url_has_allowed_host_and_scheme(referer, {request.get_host()})
            else reverse("home")
        )
        return render(request, "web/list_signup.html", ctx)


class ListConfirmView(View):
    """Placeholder so the emailed link resolves; Task 3 replaces it."""

    def get(self, request, token):
        raise Http404
