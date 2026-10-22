"""Staff pages for online ticket orders.

The summary shows what each showtime has sold online; the order log lists
every order. On the door list for one showtime staff tick buyers off as
they arrive, set how many seats go online, resend a failed ticket email,
refund one order, or refund every order when the showtime is cancelled.
"""

import datetime
import json
from decimal import Decimal

from boxoffice.gateway import get_gateway, square_enabled
from tickets.tiers import ONLINE_TIERS
from cinema.models import Showtime
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.views import View
from tickets.availability import check, sold_and_gross
from tickets.models import TicketOrder
from tickets.orders import resend
from tickets.refunds import refund_order, refund_showtime

from .csv_export import safe_csv_writer
from .mixins import StaffRequiredMixin
from .views import CINEMA_TZ, INVALID_ALLOWANCE, _parse_allowance

CSV_TIME = "%Y-%m-%d %H:%M"
CSV_HEADER = [
    "number",
    "first name",
    "last name",
    "email",
    "phone",
    *ONLINE_TIERS,
    "total",
    "status",
    "paid at",
    "arrived at",
]
NOT_CANCELLED = "This showtime isn't cancelled; nothing was refunded."
PER_PAGE = 50
SUMMARY_TABS = ("upcoming", "past")
LOG_ROW = "log"  # posted by the order log's buttons: answer with a log row


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
        .order_by("last_name", "first_name", "pk")
    )


def _search(orders, q: str):
    if not q:
        return orders
    return orders.filter(
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(number__icontains=q)
    )


def _count_context(showtime: Showtime) -> dict:
    availability = check(
        showtime, timezone.now(), square_enabled=square_enabled()
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


def _with_show(orders):
    """Orders with what their rows and CSV lines show: lines, show, arrival."""
    return orders.select_related(
        "redeemed_by", "showtime__engagement"
    ).prefetch_related("lines", "showtime__engagement__engagement_films__film")


def _with_toast(resp: HttpResponse, kind: str, message: str) -> HttpResponse:
    resp["HX-Trigger"] = json.dumps(
        {"dashboard-toast": {"kind": kind, "message": message}}
    )
    return resp


def _row_response(request, pk, toast: tuple[str, str] | None = None):
    """The order's row, read fresh; a redirect to the list without HTMX.

    The door list and the order log share the action endpoints; a log
    button posts row=log to get the log's row (and list) back.
    """
    from_log = request.POST.get("row") == LOG_ROW
    order = get_object_or_404(_with_show(TicketOrder.objects), pk=pk)
    if not request.headers.get("HX-Request"):
        if toast:
            messages.add_message(request, getattr(messages, toast[0].upper()), toast[1])
        if from_log:
            return redirect("dashboard:ticket_orders")
        return redirect("dashboard:showtime_orders", order.showtime_id)
    template = (
        "dashboard/_ticket_log_row.html"
        if from_log
        else "dashboard/_ticket_order_row.html"
    )
    resp = render(request, template, {"order": order})
    return _with_toast(resp, *toast) if toast else resp


class ShowtimeOrdersView(StaffRequiredMixin, View):
    """The door list; an HTMX request (the search box) gets just the rows."""

    permission_required = "tickets.view_ticketorder"

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


def _csv_response(filename: str, header: list[str]):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = safe_csv_writer(response)
    writer.writerow(header)
    return response, writer


def _csv_row(order: TicketOrder) -> list:
    """One order under CSV_HEADER."""
    quantities = {line.tier: line.quantity for line in order.lines.all()}
    return [
        order.number,
        order.first_name,
        order.last_name,
        order.email,
        order.phone,
        *(quantities.get(tier, 0) for tier in ONLINE_TIERS),
        f"{order.total_dollars:.2f}",
        order.get_status_display(),
        _csv_time(order.paid_at),
        _csv_time(order.redeemed_at),
    ]


def _csv_time(value) -> str:
    return value.astimezone(CINEMA_TZ).strftime(CSV_TIME) if value else ""


class ShowtimeOrdersExportView(StaffRequiredMixin, View):
    permission_required = "tickets.view_ticketorder"

    def get(self, request, pk):
        showtime = _get_showtime(pk)
        local = showtime.starts_at.astimezone(CINEMA_TZ)
        response, writer = _csv_response(
            f"orders-{local:%Y-%m-%d-%H%M}.csv", CSV_HEADER
        )
        for order in _door_orders(showtime):
            writer.writerow(_csv_row(order))
        return response


class ShowtimeAllowanceView(StaffRequiredMixin, View):
    """Set the online allowance from the door list; blank means the default."""

    permission_required = "cinema.change_showtime"

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

    permission_required = "tickets.change_ticketorder"

    def post(self, request, pk):
        showtime = _get_showtime(pk)
        # The banner only shows on a cancelled showtime, but a stale tab or a
        # double submit could still post here.
        if not showtime.is_cancelled:
            kind, message = "error", NOT_CANCELLED
        else:
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
    permission_required = "tickets.change_ticketorder"

    def post(self, request, pk):
        order = get_object_or_404(TicketOrder, pk=pk)
        if order.counts_as_sold and order.redeemed_at is None:
            order.redeemed_at = timezone.now()
            order.redeemed_by = request.user
            order.save(update_fields=["redeemed_at", "redeemed_by"])
        return _row_response(request, pk)


class TicketOrderUnarriveView(StaffRequiredMixin, View):
    permission_required = "tickets.change_ticketorder"

    def post(self, request, pk):
        order = get_object_or_404(TicketOrder, pk=pk)
        order.redeemed_at = None
        order.redeemed_by = None
        order.save(update_fields=["redeemed_at", "redeemed_by"])
        return _row_response(request, pk)


class TicketOrderRetryView(StaffRequiredMixin, View):
    """Send the ticket email again for a paid order whose email failed."""

    permission_required = "tickets.change_ticketorder"

    def post(self, request, pk):
        order = get_object_or_404(TicketOrder, pk=pk)
        if order.status != TicketOrder.Status.FAILED or not order.square_payment_id:
            # Already sent (a double click or a stale row), or never paid.
            return _row_response(request, pk, ("info", "Nothing to resend"))
        order = resend(order)
        if order.status == TicketOrder.Status.PAID:
            toast = ("success", f"Ticket emailed to {order.email}")
        else:
            toast = ("error", order.error)
        return _row_response(request, pk, toast)


class TicketOrderRefundView(StaffRequiredMixin, View):
    permission_required = "tickets.change_ticketorder"

    def post(self, request, pk):
        order = get_object_or_404(TicketOrder, pk=pk)
        if not order.counts_as_sold:
            return _row_response(request, pk, ("info", "Already refunded"))
        order = refund_order(order, reason="Refunded by staff", gateway=get_gateway())
        if order.status == TicketOrder.Status.REFUNDED and order.error:
            toast = ("warning", f"Refunded {order.number}. {order.error}")
        elif order.status == TicketOrder.Status.REFUNDED:
            toast = ("success", f"Refunded {order.number}")
        else:
            toast = ("error", order.error)
        return _row_response(request, pk, toast)


def _midnight(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time.min, tzinfo=CINEMA_TZ)


def _dollars(cents: int) -> Decimal:
    return Decimal(cents) / 100


def _showtimes():
    return Showtime.objects.select_related("engagement", "screen").prefetch_related(
        "engagement__engagement_films__film"
    )


def _totals(today: datetime.date) -> dict:
    """Online tickets and gross for today's shows and the seven days from today."""
    week = list(
        Showtime.objects.filter(
            starts_at__gte=_midnight(today),
            starts_at__lt=_midnight(today + datetime.timedelta(days=7)),
        ).only("pk", "starts_at")
    )
    sales = sold_and_gross(week)
    tomorrow = _midnight(today + datetime.timedelta(days=1))
    totals = {}
    for key, showtimes in (
        ("today", [st for st in week if st.starts_at < tomorrow]),
        ("week", week),
    ):
        rows = [sales.get(st.pk, (0, 0)) for st in showtimes]
        totals[key] = {
            "tickets": sum(tickets for tickets, _ in rows),
            "gross_dollars": _dollars(sum(cents for _, cents in rows)),
        }
    return totals


def _day_label(day: datetime.date, today: datetime.date) -> str:
    if day == today:
        return "Today"
    if day == today + datetime.timedelta(days=1):
        return "Tomorrow"
    return format_date(day, "l, F j, Y")


def _days(showtimes, today: datetime.date) -> list[dict]:
    """The showtimes, in the order given, grouped by their Eastern day."""
    showtimes = list(showtimes)
    sales = sold_and_gross(showtimes)
    days = []
    for st in showtimes:
        day = st.starts_at.astimezone(CINEMA_TZ).date()
        if not days or days[-1]["date"] != day:
            days.append({"date": day, "label": _day_label(day, today), "rows": []})
        tickets, cents = sales.get(st.pk, (0, 0))
        days[-1]["rows"].append(
            {
                "st": st,
                "sold": tickets,
                "gross_dollars": _dollars(cents),
                "allowance": st.effective_online_allowance,
            }
        )
    return days


class TicketSummaryView(StaffRequiredMixin, View):
    """Online sales per showtime: upcoming from today, or past (paginated)."""

    permission_required = "tickets.view_ticketorder"

    def get(self, request):
        tab = request.GET.get("tab")
        tab = tab if tab in SUMMARY_TABS else SUMMARY_TABS[0]
        today = timezone.localdate()
        page_obj = None
        if tab == "upcoming":
            showtimes = _showtimes().filter(starts_at__gte=_midnight(today))
            showtimes = showtimes.order_by("starts_at", "pk")
        else:
            past = _showtimes().filter(starts_at__lt=_midnight(today))
            paginator = Paginator(past.order_by("-starts_at", "-pk"), PER_PAGE)
            page_obj = paginator.get_page(request.GET.get("page"))
            showtimes = page_obj.object_list
        ctx = {
            "tab": tab,
            "tabs": SUMMARY_TABS,
            "totals": _totals(today),
            "days": _days(showtimes, today),
            "page_obj": page_obj,
        }
        return render(request, "dashboard/tickets.html", ctx)


def _log_orders(request) -> tuple:
    """Every order, newest first, narrowed by a known ?status=; and that status."""
    status = request.GET.get("status", "")
    orders = _with_show(TicketOrder.objects.order_by("-created_at", "-pk"))
    if status in TicketOrder.Status.values:
        return orders.filter(status=status), status
    return orders, ""


class TicketOrderListView(StaffRequiredMixin, View):
    permission_required = "tickets.view_ticketorder"

    def get(self, request):
        orders, status = _log_orders(request)
        page_obj = Paginator(orders, PER_PAGE).get_page(request.GET.get("page"))
        ctx = {
            "page_obj": page_obj,
            "status": status,
            "statuses": TicketOrder.Status.choices,
        }
        return render(request, "dashboard/ticket_orders.html", ctx)


class TicketOrderLogExportView(StaffRequiredMixin, View):
    """The order log as CSV: the door-list columns after the film and showtime."""

    permission_required = "tickets.view_ticketorder"

    def get(self, request):
        orders, status = _log_orders(request)
        suffix = f"-{status.lower()}" if status else ""
        response, writer = _csv_response(
            f"ticket-orders-{timezone.localdate():%Y-%m-%d}{suffix}.csv",
            ["film", "showtime", *CSV_HEADER],
        )
        for order in orders:
            show = order.showtime
            writer.writerow(
                [show.engagement.title, _csv_time(show.starts_at), *_csv_row(order)]
            )
        return response
