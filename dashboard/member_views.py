"""Staff surface for the membership roster.

Replaces a spreadsheet. Memberships are still sold through Square payment
links; nothing here talks to Square, and nothing here is public — members
are the first real customer PII in this database, so every view is
staff-only, the CSV export included.
"""

from audience.models import Member
from django.db import models
from django.shortcuts import render
from django.views import View
from web.constants import MEMBERSHIP_TIER_LABELS

from .mixins import StaffRequiredMixin

STATUS_FILTERS = [
    ("", "All members"),
    ("active", "Active"),
    ("expiring", "Expiring soon"),
    ("lapsed", "Lapsed"),
]


def member_roster(request):
    """The roster as filtered by ?q= and ?status=.

    Status is derived from dates rather than stored, so the status filter
    runs in Python over the prefetched terms. The roster is a few hundred
    rows at most; a query that could express "expiring soon" in SQL would
    duplicate the definition that lives on the model.
    """
    members = Member.objects.prefetch_related("terms")

    q = (request.GET.get("q") or "").strip()
    if q:
        members = members.filter(
            models.Q(first_name__icontains=q)
            | models.Q(last_name__icontains=q)
            | models.Q(email__icontains=q)
        )

    status = (request.GET.get("status") or "").strip()
    valid = {value for value, _label in STATUS_FILTERS if value}
    members = list(members)
    if status in valid:
        members = [m for m in members if m.status == status]
    return members, q, status


class MemberListView(StaffRequiredMixin, View):
    def get(self, request):
        members, q, status = member_roster(request)
        return render(
            request,
            "dashboard/members.html",
            {
                "members": members,
                "q": q,
                "selected_status": status,
                "statuses": STATUS_FILTERS,
                "tier_labels": MEMBERSHIP_TIER_LABELS,
                "active_count": Member.objects.active().count(),
            },
        )
