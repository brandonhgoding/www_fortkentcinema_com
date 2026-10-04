"""Every membership term, across all members.

The member detail page answers "what has this person bought". This page
answers the two questions that need the whole set: whose membership is
about to lapse, and what did memberships actually bring in over a period.
The roster's status filter can't answer either — it collapses a member to
their current term, so renewals and past years are invisible there.

Unlike the roster, the filters here run in SQL: this table grows by one row
per renewal per member per year and has no ceiling, where the roster is
bounded by the number of people.
"""

import csv
import datetime

from audience.models import MembershipTerm, MembershipTier, MemberStatus
from audience.models.member import EXPIRING_SOON_DAYS
from django.db.models import Exists, OuterRef, Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from .mixins import StaffRequiredMixin

WINDOW_FILTERS = [
    ("", "All terms"),
    ("current", "Current"),
    # The roster's words for the same states, so the two screens agree.
    ("expiring", MemberStatus.EXPIRING.label),
    ("expired", "Expired"),
    ("future", MemberStatus.UPCOMING.label),
]


def _window_q(window: str, today: datetime.date) -> Q | None:
    soon = today + datetime.timedelta(days=EXPIRING_SOON_DAYS)
    return {
        "current": MembershipTerm.covering(today),
        # A subset of "current" on purpose: a term that has already expired
        # is not expiring soon, it is expired.
        # Also excludes a term the member has already renewed: one that
        # another of their terms continues without a gap is not about to
        # lapse, which is what Member.status judges too.
        "expiring": Q(
            ~Exists(
                MembershipTerm.objects.filter(
                    member=OuterRef("member"),
                    started_on__lte=OuterRef("expires_on") + datetime.timedelta(days=1),
                    expires_on__gt=OuterRef("expires_on"),
                )
            ),
            MembershipTerm.covering(today),
            expires_on__lte=soon,
        ),
        "expired": Q(expires_on__lt=today),
        "future": Q(started_on__gt=today),
    }.get(window)


def _parse_date(raw: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return None


def term_ledger(request) -> dict:
    """The filtered term list plus the filter state the template echoes back.

    Bad dates in `?from=`/`?to=` are dropped rather than raising: these are
    hand-editable URL parameters, and a typo should show the unfiltered
    range with an empty box, not a 500.
    """
    params = request.GET
    today = timezone.localdate()
    terms = MembershipTerm.objects.select_related("member", "tier")

    q = (params.get("q") or "").strip()
    if q:
        terms = terms.filter(
            Q(member__first_name__icontains=q)
            | Q(member__last_name__icontains=q)
            | Q(member__email__icontains=q)
        )

    tier_slug = (params.get("tier") or "").strip()
    if tier_slug:
        terms = terms.filter(tier__slug=tier_slug)

    window = (params.get("window") or "").strip()
    window_q = _window_q(window, today)
    if window_q is not None:
        terms = terms.filter(window_q)
    else:
        window = ""

    started_from = _parse_date((params.get("from") or "").strip())
    started_to = _parse_date((params.get("to") or "").strip())
    if started_from:
        terms = terms.filter(started_on__gte=started_from)
    if started_to:
        terms = terms.filter(started_on__lte=started_to)

    # Soonest-expiring first when the question is "who is about to lapse";
    # newest-first (the model default) when it is "what did we sell".
    if window in ("current", "expiring", "future"):
        terms = terms.order_by("expires_on", "member__last_name")

    # Aggregated over the filtered queryset rather than summed in the
    # template, so the total is right even though the page prints every row
    # today and may paginate later.
    totals = terms.aggregate(revenue=Sum("price_paid"))

    return {
        "terms": terms,
        "q": q,
        "selected_tier": tier_slug,
        "selected_window": window,
        "started_from": started_from.isoformat() if started_from else "",
        "started_to": started_to.isoformat() if started_to else "",
        "windows": WINDOW_FILTERS,
        "tiers": MembershipTier.objects.all(),
        "term_count": terms.count(),
        "revenue": totals["revenue"] or 0,
        "today": today,
    }


class TermLedgerView(StaffRequiredMixin, View):
    def get(self, request):
        return render(request, "dashboard/terms.html", term_ledger(request))


class TermExportView(StaffRequiredMixin, View):
    """One row per term, honouring the same filters as the screen.

    The member export is one row per member, from their latest term — it
    answers "who are my members". This one answers "what did we sell", so
    a member who has renewed four times appears four times.
    """

    def get(self, request):
        ledger = term_ledger(request)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="membership-terms.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "first_name", "last_name", "email", "tier",
            "started_on", "expires_on", "price_paid", "purchased_at", "notes",
        ])
        for term in ledger["terms"]:
            writer.writerow([
                term.member.first_name,
                term.member.last_name,
                term.member.email,
                term.tier.slug,
                term.started_on.isoformat(),
                term.expires_on.isoformat(),
                term.price_paid,
                term.purchased_at.isoformat() if term.purchased_at else "",
                term.notes,
            ])
        return response
