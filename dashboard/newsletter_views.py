"""Staff view of the Thursday email: one row per week, and a preview of the
stored body. Read-only: the send is automatic (the owner's call, 2026-10-30)."""

from django.db.models import Prefetch
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

from newsletter.models import Delivery, Issue

from .mixins import StaffRequiredMixin

# The design system's badge colours, by Issue status.
BADGE = {
    Issue.Status.SENT: "status-active",
    Issue.Status.SKIPPED: "status-ended",
    Issue.Status.SENDING: "status-pending",
    Issue.Status.FAILED: "status-closed",
}


class IssueListView(StaffRequiredMixin, View):
    permission_required = "newsletter.view_issue"

    def get(self, request):
        # Only the failures come along: a year of sent rows stays in the DB.
        failed = Prefetch(
            "deliveries",
            queryset=Delivery.objects.filter(
                status=Delivery.Status.FAILED
            ).select_related("subscriber"),
            to_attr="failed",
        )
        rows = [
            {
                "issue": issue,
                "badge": BADGE.get(issue.status, ""),
                "failed": issue.failed,
            }
            for issue in Issue.objects.prefetch_related(failed)
        ]
        return render(request, "dashboard/newsletter_issues.html", {"rows": rows})


class IssuePreviewView(StaffRequiredMixin, View):
    permission_required = "newsletter.view_issue"

    def get(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if issue is None:
            raise Http404
        response = HttpResponse(issue.preview_html, content_type="text/html")
        # Stored HTML, shown inside the dashboard: never let it script it.
        response["Content-Security-Policy"] = "sandbox"
        return response
