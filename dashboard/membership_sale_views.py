"""Staff surface for Square membership sales: the list and the Retry button.

The webhook records every membership order as a MembershipSale. Most are
entered without anyone looking; the ones that could not be (an unmatched
tier, a Square outage) sit as "Needs attention" until staff retry them here.
"""

import json

from boxoffice.memberships import process_order
from boxoffice.models import MembershipSale
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .mixins import StaffRequiredMixin


class SquareSaleListView(StaffRequiredMixin, View):
    def get(self, request):
        sales = MembershipSale.objects.select_related("tier", "term__member")
        failed_count = MembershipSale.objects.filter(
            status=MembershipSale.Status.FAILED
        ).count()
        return render(
            request,
            "dashboard/square_sales.html",
            {"sales": sales, "failed_count": failed_count},
        )


def _toast_for(sale: MembershipSale) -> dict:
    if sale.status == MembershipSale.Status.OK:
        return {"kind": "success", "message": f"Entered: {sale.display_name}"}
    if sale.status == MembershipSale.Status.SKIPPED:
        return {"kind": "error", "message": "Skipped"}
    return {"kind": "error", "message": sale.error}


class SquareSaleRetryView(StaffRequiredMixin, View):
    def post(self, request, pk):
        sale = get_object_or_404(MembershipSale, pk=pk)
        # Never raises on gateway failure: the outcome lands on the row.
        process_order(sale.order_id)
        if not request.headers.get("HX-Request"):
            return redirect("dashboard:square_sales")
        sale = MembershipSale.objects.select_related("tier", "term__member").get(
            pk=pk
        )
        resp = render(request, "dashboard/_square_sale_row.html", {"sale": sale})
        resp["HX-Trigger"] = json.dumps({"dashboard-toast": _toast_for(sale)})
        return resp
