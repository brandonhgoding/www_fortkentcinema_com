"""Staff surface for advertising inquiries.

Nothing here sends mail — this list plus the NEW count on the
dashboard home is how an ad lead reaches a human.
"""

from cinema.models import AdInquiry, InquiryStatus
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .mixins import StaffRequiredMixin


class AdInquiryListView(StaffRequiredMixin, View):
    def get(self, request):
        inquiries = AdInquiry.objects.all()

        status = (request.GET.get("status") or "").strip()
        if status in InquiryStatus.values:
            inquiries = inquiries.filter(status=status)

        return render(
            request,
            "dashboard/ad_inquiries.html",
            {
                "inquiries": inquiries,
                "new_count": AdInquiry.objects.filter(
                    status=InquiryStatus.NEW
                ).count(),
                "statuses": InquiryStatus.choices,
                "selected_status": status,
            },
        )


class AdInquiryStatusView(StaffRequiredMixin, View):
    def post(self, request, pk: int):
        inquiry = get_object_or_404(AdInquiry, pk=pk)
        status = (request.POST.get("status") or "").strip()
        if status in InquiryStatus.values:
            inquiry.status = status
            inquiry.save(update_fields=["status"])
        return redirect("dashboard:ad_inquiries")
