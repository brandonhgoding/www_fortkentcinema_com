"""Staff surface for membership link requests.

A member whose roster row carries another email asks, from the member home,
to have it linked to their account. Nothing here sends mail: this list plus
the open count on the dashboard home is how the ask reaches a human. Staff
link it by editing the roster row's email to the account email; the member's
next visit closes the request, or staff mark it done here.
"""

from audience.models import LinkRequestStatus, MembershipLinkRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .mixins import StaffRequiredMixin


class LinkRequestListView(StaffRequiredMixin, View):
    permission_required = "audience.view_membershiplinkrequest"

    def get(self, request):
        requests = MembershipLinkRequest.objects.select_related("user")

        status = (request.GET.get("status") or "").strip()
        if status in LinkRequestStatus.values:
            requests = requests.filter(status=status)

        return render(
            request,
            "dashboard/membership_link_requests.html",
            {
                "requests": requests,
                "open_count": MembershipLinkRequest.objects.filter(
                    status=LinkRequestStatus.NEW
                ).count(),
                "statuses": LinkRequestStatus.choices,
                "selected_status": status,
            },
        )


class LinkRequestStatusView(StaffRequiredMixin, View):
    permission_required = "audience.change_membershiplinkrequest"

    def post(self, request, pk: int):
        ask = get_object_or_404(MembershipLinkRequest, pk=pk)
        status = (request.POST.get("status") or "").strip()
        if status == LinkRequestStatus.DONE:
            ask.mark_done()
        elif status == LinkRequestStatus.NEW:
            ask.reopen()
        return redirect("dashboard:membership_link_requests")
