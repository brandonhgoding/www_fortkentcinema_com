"""Staff surface for the email list.

Nothing in this project sends mail yet, so the CSV export IS the delivery
mechanism: close a round, export, paste into Square Marketing. Unsubscribes
are filtered here rather than only in the database, so an opt-out cannot
leak into a send.
"""

from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from audience.models import Subscriber

from .csv_export import safe_csv_writer
from .mixins import StaffRequiredMixin


class SubscriberListView(StaffRequiredMixin, View):
    def get(self, request):
        subscribers = Subscriber.objects.all()
        return render(
            request,
            "dashboard/subscribers.html",
            {
                "subscribers": subscribers,
                "active_count": Subscriber.objects.active().count(),
            },
        )


class SubscriberExportView(StaffRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="subscribers.csv"'
        )

        writer = safe_csv_writer(response)
        writer.writerow(["email", "source", "consent_at"])
        for sub in Subscriber.objects.active().order_by("consent_at"):
            writer.writerow(
                [sub.email, sub.source, sub.consent_at.isoformat()]
            )
        return response
