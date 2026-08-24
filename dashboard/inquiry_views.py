"""Staff surface for sponsorship inquiries.

Nothing here sends mail either — see subscriber_views. This list plus the
NEW count on the dashboard home is how a lead reaches a human.
"""

from cinema.models import InquiryStatus, SponsorshipInquiry
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from web.constants import SPONSORSHIP_TIER_LABELS

from .mixins import StaffRequiredMixin


class InquiryListView(StaffRequiredMixin, View):
    def get(self, request):
        inquiries = SponsorshipInquiry.objects.select_related("studio_title")

        status = (request.GET.get("status") or "").strip()
        if status in InquiryStatus.values:
            inquiries = inquiries.filter(status=status)

        return render(
            request,
            "dashboard/inquiries.html",
            {
                "inquiries": inquiries,
                "new_count": SponsorshipInquiry.objects.filter(
                    status=InquiryStatus.NEW
                ).count(),
                "statuses": InquiryStatus.choices,
                "selected_status": status,
                "tier_labels": SPONSORSHIP_TIER_LABELS,
            },
        )


class InquiryStatusView(StaffRequiredMixin, View):
    def post(self, request, pk: int):
        inquiry = get_object_or_404(SponsorshipInquiry, pk=pk)
        status = (request.POST.get("status") or "").strip()
        if status in InquiryStatus.values:
            inquiry.status = status
            inquiry.save(update_fields=["status"])
        return redirect("dashboard:inquiries")
