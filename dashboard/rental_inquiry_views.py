"""Staff surface for rental inquiries.

The rentals twin of inquiry_views, kept as its own page rather than a second
table on that one: the two leads have different columns and different
follow-ups, and one status filter driving two tables would be a filter on
neither. Nothing here sends mail — this list plus the NEW count on the
dashboard home is how a booking request reaches a human.
"""

from cinema.models import InquiryStatus, RentalInquiry
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .mixins import StaffRequiredMixin


class RentalInquiryListView(StaffRequiredMixin, View):
    def get(self, request):
        inquiries = RentalInquiry.objects.all()

        status = (request.GET.get("status") or "").strip()
        if status in InquiryStatus.values:
            inquiries = inquiries.filter(status=status)

        return render(
            request,
            "dashboard/rental_inquiries.html",
            {
                "inquiries": inquiries,
                "new_count": RentalInquiry.objects.filter(
                    status=InquiryStatus.NEW
                ).count(),
                "statuses": InquiryStatus.choices,
                "selected_status": status,
            },
        )


class RentalInquiryStatusView(StaffRequiredMixin, View):
    def post(self, request, pk: int):
        inquiry = get_object_or_404(RentalInquiry, pk=pk)
        status = (request.POST.get("status") or "").strip()
        if status in InquiryStatus.values:
            inquiry.status = status
            inquiry.save(update_fields=["status"])
        return redirect("dashboard:rental_inquiries")
