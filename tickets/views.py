"""The public ticket pages: buy for a showtime, then the order's own page."""

import datetime

from boxoffice.gateway import get_gateway
from cinema.models import Showtime
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from web.services.cinema_data import CINEMA_TZ, OPEN_CAPTIONS_NOTE, _format_runtime

from tickets import availability, orders, pricing
from tickets.forms import BuyForm
from tickets.mail import qr_png, ticket_context
from tickets.models import TicketOrder
from tickets.spec import base_url

DOOR = "Online tickets aren't available for this show. Buy at the door."
NOT_ON_SALE = "This showtime isn't on sale."

# Why a showtime cannot be bought online, keyed by availability reason.
CLOSED_SENTENCES = {
    "disabled": DOOR,
    "no_item": DOOR,
    "not_listed": NOT_ON_SALE,
    "cancelled": NOT_ON_SALE,
    "cutoff": (
        "Online sales for this show have closed. "
        "Tickets are still available at the door."
    ),
    "sold_out": "Sold out online. Tickets may still be available at the door.",
    "quantity": "Pick at least one ticket.",
}
CHECKOUT_FAILED = "We couldn't start checkout. Please try again, or buy at the door."

# "N left online" only once the count is worth a hurry.
FEW_LEFT = 10
# The order page refreshes itself this long while Square confirms the payment.
CONFIRMING_FOR = datetime.timedelta(minutes=2)
# A PENDING order this old asks Square directly, in case the webhook was lost.
RECOVER_AFTER = datetime.timedelta(seconds=60)


def _see_other(url: str) -> HttpResponseRedirect:
    """A 303: the browser follows a POST's redirect with a GET."""
    response = HttpResponseRedirect(url)
    response.status_code = 303
    return response


def _dollars(cents: int) -> str:
    return f"${cents // 100}" if cents % 100 == 0 else f"${cents / 100:.2f}"


class BuyView(View):
    """GET /tickets/<pk>/ shows the form; POST holds the seats and sends the
    buyer to Square's checkout."""

    def get(self, request, pk):
        showtime = self._showtime(pk)
        return self._render(request, showtime, BuyForm(), gateway=get_gateway())

    def post(self, request, pk):
        showtime = self._showtime(pk)
        form = BuyForm(request.POST)
        if form.is_bot:
            return _see_other(reverse("tickets:buy", args=[pk]))
        gateway = get_gateway()
        if gateway is None or not form.is_valid():
            # Without Square the page shows the closed sentence, not the form.
            return self._render(request, showtime, form, gateway=gateway)
        try:
            order = orders.start(
                showtime,
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
                phone=form.cleaned_data["phone"],
                quantities=form.quantities(),
                now=timezone.now(),
                gateway=gateway,
            )
        except orders.Refused as refused:
            error = CLOSED_SENTENCES[refused.reason]
            return self._render(request, showtime, form, gateway=gateway, error=error)
        if order.status == TicketOrder.Status.FAILED:
            return self._render(
                request, showtime, form, gateway=gateway, error=CHECKOUT_FAILED
            )
        return _see_other(order.square_checkout_url)

    def _showtime(self, pk) -> Showtime:
        """The showtime, or 404 for a draft or hidden run (availability's
        "not_listed"), whatever the Square setting."""
        showtime = get_object_or_404(
            Showtime.objects.select_related("engagement", "screen"), pk=pk
        )
        if not availability.is_listed(showtime.engagement):
            raise Http404
        return showtime

    def _render(self, request, showtime, form, *, gateway, error=""):
        result = availability.check(
            showtime, timezone.now(), square_enabled=gateway is not None
        )
        film = showtime.engagement.primary_film
        starts_at = showtime.starts_at.astimezone(CINEMA_TZ)
        rows = pricing.price_table(showtime.starts_at)
        context = {
            "showtime": showtime,
            "movie": {
                "title": showtime.engagement.title,
                "poster": (film.poster_url if film else "") or "",
                "rating": (film.rating if film else "") or "",
                "runtime": _format_runtime(film.runtime_minutes if film else None),
                "language_label": showtime.engagement.language_label,
                "captions_note": (
                    OPEN_CAPTIONS_NOTE if showtime.captions == "OC" else ""
                ),
            },
            "day": starts_at.strftime("%A, %B %-d"),
            "time": starts_at.strftime("%-I:%M %p"),
            "is_matinee": pricing.is_matinee(showtime.starts_at),
            "rows": rows,
            "tickets": [
                {"row": row, "price": _dollars(row.unit_cents), "field": form[row.tier]}
                for row in rows
            ],
            "availability": result,
            "closed_sentence": CLOSED_SENTENCES.get(result.reason, ""),
            "few_left": result.remaining < FEW_LEFT,
            "form": form,
            "contact_fields": [
                form["first_name"],
                form["last_name"],
                form["email"],
                form["phone"],
            ],
            "error": error,
        }
        return render(request, "tickets/buy.html", context)


def order_state(order: TicketOrder, now: datetime.datetime) -> str:
    """Which version of the order page to show."""
    if order.counts_as_sold:
        return "paid"
    if order.status == TicketOrder.Status.PENDING:
        return "pending" if order.created_at > now - CONFIRMING_FOR else "waiting"
    return order.status.lower()


class OrderView(View):
    """GET /tickets/order/<token>/: the ticket once paid, else where it stands."""

    def get(self, request, token):
        order = get_object_or_404(
            TicketOrder.objects.select_related(
                "showtime__engagement", "showtime__screen"
            ),
            token=token,
        )
        now = timezone.now()
        if (
            order.status == TicketOrder.Status.PENDING
            and order.created_at <= now - RECOVER_AFTER
        ):
            orders.recover_pending(order, gateway=get_gateway())
        context = {
            **ticket_context(order),
            "state": order_state(order, now),
            "refunded_on": (
                order.refunded_at.astimezone(CINEMA_TZ).strftime("%a %b %-d")
                if order.refunded_at
                else ""
            ),
        }
        return render(request, "tickets/order.html", context)


def order_qr(request, token):
    """The ticket's QR code as a PNG; only for an order that has a ticket."""
    order = get_object_or_404(TicketOrder, token=token)
    if not order.counts_as_sold:
        raise Http404
    url = base_url() + reverse("tickets:order", args=[order.token])
    response = HttpResponse(qr_png(url), content_type="image/png")
    response["Cache-Control"] = "private, max-age=86400"
    return response
