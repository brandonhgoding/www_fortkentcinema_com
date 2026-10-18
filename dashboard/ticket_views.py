"""Staff pages for online ticket orders: the door list for one showtime.

Staff tick buyers off as they arrive, set how many seats go online, resend
a failed ticket email, refund one order, or refund every order when the
showtime is cancelled.
"""

import json

from boxoffice.gateway import get_gateway
from boxoffice.spec import SQUARE_TIERS
from cinema.models import Showtime
from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from tickets.availability import check
from tickets.models import TicketOrder
from tickets.orders import resend
from tickets.refunds import refund_order, refund_showtime

from .csv_export import safe_csv_writer
from .mixins import StaffRequiredMixin
from .views import CINEMA_TZ, INVALID_ALLOWANCE, _parse_allowance

CSV_TIME = "%Y-%m-%d %H:%M"


def _get_showtime(pk) -> Showtime:
    return get_object_or_404(
        Showtime.objects.select_related("engagement", "screen"), pk=pk
    )


def _door_orders(showtime: Showtime):
    """The orders on the door list: sold (see counts_as_sold) or refunded."""
    return (
        TicketOrder.objects.filter(showtime=showtime)
        .filter(
            Q(status__in=[TicketOrder.Status.PAID, TicketOrder.Status.REFUNDED])
            | (Q(status=TicketOrder.Status.FAILED) & ~Q(square_payment_id=""))
        )
        .select_related("redeemed_by")
        .prefetch_related("lines")
        .order_by("name", "pk")
    )


def _search(orders, q: str):
    if not q:
        return orders
    return orders.filter(Q(name__icontains=q) | Q(number__icontains=q))


def _count_context(showtime: Showtime) -> dict:
    availability = check(
        showtime, timezone.now(), square_enabled=bool(settings.SQUARE_ACCESS_TOKEN)
    )
    return {
        "showtime": showtime,
        "sold": availability.sold,
        "allowance": availability.allowance,
        "allowance_value": (
            "" if showtime.online_allowance is None else showtime.online_allowance
        ),
    }


def _page_context(showtime: Showtime, q: str = "") -> dict:
    refundable = []
    if showtime.is_cancelled:
        refundable = [o for o in _door_orders(showtime) if o.counts_as_sold]
    return {
        **_count_context(showtime),
        "orders": _search(_door_orders(showtime), q),
        "q": q,
        "refundable_count": len(refundable),
        "refundable_dollars": sum(o.total_dollars for o in refundable),
    }


def _with_toast(resp: HttpResponse, kind: str, message: str) -> HttpResponse:
    resp["HX-Trigger"] = json.dumps(
        {"dashboard-toast": {"kind": kind, "message": message}}
    )
    return resp


def _row_response(request, pk, toast: tuple[str, str] | None = None):
    """The order's row, read fresh; a redirect to the list without HTMX."""
    order = get_object_or_404(
        TicketOrder.objects.select_related("redeemed_by").prefetch_related("lines"),
        pk=pk,
    )
    if not request.headers.get("HX-Request"):
        if toast:
            messages.add_message(request, getattr(messages, toast[0].upper()), toast[1])
        return redirect("dashboard:showtime_orders", order.showtime_id)
    resp = render(request, "dashboard/_ticket_order_row.html", {"order": order})
    return _with_toast(resp, *toast) if toast else resp


class ShowtimeOrdersView(StaffRequiredMixin, View):
    """The door list; an HTMX request (the search box) gets just the rows."""

    def get(self, request, pk):
        showtime = _get_showtime(pk)
        q = request.GET.get("q", "").strip()
        if request.headers.get("HX-Request"):
            orders = _search(_door_orders(showtime), q)
            return render(
                request, "dashboard/_ticket_order_rows.html", {"orders": orders, "q": q}
            )
        return render(
            request, "dashboard/showtime_orders.html", _page_context(showtime, q)
        )


class ShowtimeOrdersExportView(StaffRequiredMixin, View):
    def get(self, request, pk):
        showtime = _get_showtime(pk)
        local = showtime.starts_at.astimezone(CINEMA_TZ)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="orders-{local:%Y-%m-%d-%H%M}.csv"'
        )
        writer = safe_csv_writer(response)
        writer.writerow(
            [
                "number",
                "name",
                "email",
                "phone",
                *SQUARE_TIERS,
                "total",
                "status",
                "paid at",
                "arrived at",
            ]
        )
        for order in _door_orders(showtime):
            quantities = {line.tier: line.quantity for line in order.lines.all()}
            writer.writerow(
                [
                    order.number,
                    order.name,
                    order.email,
                    order.phone,
                    *(quantities.get(tier, 0) for tier in SQUARE_TIERS),
                    f"{order.total_dollars:.2f}",
                    order.get_status_display(),
                    _csv_time(order.paid_at),
                    _csv_time(order.redeemed_at),
                ]
            )
        return response


def _csv_time(value) -> str:
    return value.astimezone(CINEMA_TZ).strftime(CSV_TIME) if value else ""


class ShowtimeAllowanceView(StaffRequiredMixin, View):
    """Set the online allowance from the door list; blank means the default."""

    def post(self, request, pk):
        showtime = _get_showtime(pk)
        raw = request.POST.get("online_allowance", "")
        allowance, ok = _parse_allowance(raw)
        if not ok:
            ctx = {
                **_count_context(showtime),
                "allowance_value": raw,
                "error": INVALID_ALLOWANCE,
            }
            resp = render(request, "dashboard/_allowance_form.html", ctx, status=400)
            return _with_toast(resp, "error", INVALID_ALLOWANCE)
        showtime.online_allowance = allowance
        showtime.save(update_fields=["online_allowance"])
        if not request.headers.get("HX-Request"):
            return redirect("dashboard:showtime_orders", pk)
        resp = render(
            request, "dashboard/_allowance_form.html", _count_context(showtime)
        )
        return _with_toast(resp, "success", "Online allowance saved")


class ShowtimeRefundAllView(StaffRequiredMixin, View):
    """Refund every sold order on the showtime, then show the list again."""

    def post(self, request, pk):
        showtime = _get_showtime(pk)
        summary = refund_showtime(showtime, gateway=get_gateway())
        message = f"{summary.refunded} refunded"
        if summary.failed:
            message += f", {summary.failed} failed"
        kind = "warning" if summary.failed else "success"
        if not request.headers.get("HX-Request"):
            messages.add_message(request, getattr(messages, kind.upper()), message)
            return redirect("dashboard:showtime_orders", pk)
        resp = render(
            request, "dashboard/showtime_orders.html", _page_context(showtime)
        )
        return _with_toast(resp, kind, message)


class TicketOrderArriveView(StaffRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(TicketOrder, pk=pk)
        if order.counts_as_sold and order.redeemed_at is None:
            order.redeemed_at = timezone.now()
            order.redeemed_by = request.user
            order.save(update_fields=["redeemed_at", "redeemed_by"])
        return _row_response(request, pk)


class TicketOrderUnarriveView(StaffRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(TicketOrder, pk=pk)
        order.redeemed_at = None
        order.redeemed_by = None
        order.save(update_fields=["redeemed_at", "redeemed_by"])
        return _row_response(request, pk)


class TicketOrderRetryView(StaffRequiredMixin, View):
    """Send the ticket email again for a paid order whose email failed."""

    def post(self, request, pk):
        order = get_object_or_404(TicketOrder, pk=pk)
        order = resend(order)
        if order.status == TicketOrder.Status.PAID:
            toast = ("success", f"Ticket emailed to {order.email}")
        else:
            toast = ("error", order.error or "Nothing to resend")
        return _row_response(request, pk, toast)


class TicketOrderRefundView(StaffRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(TicketOrder, pk=pk)
        order = refund_order(order, reason="Refunded by staff", gateway=get_gateway())
        if order.status == TicketOrder.Status.REFUNDED and order.error:
            toast = ("warning", f"Refunded {order.number}. {order.error}")
        elif order.status == TicketOrder.Status.REFUNDED:
            toast = ("success", f"Refunded {order.number}")
        else:
            toast = ("error", order.error or "Nothing to refund")
        return _row_response(request, pk, toast)
