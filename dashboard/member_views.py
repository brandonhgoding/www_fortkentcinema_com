"""Staff surface for the membership roster.

Replaces a spreadsheet. Memberships are still sold through Square payment
links; nothing here talks to Square, and nothing here is public — members
are the first real customer PII in this database, so every view is
staff-only, the CSV export included.
"""

import json

from audience.dates import month_bounds
from audience.models import FreeAdmission, Member, MembershipTerm, MemberStatus
from audience.terms import latest_term, overlapping_term_ids, renewal_start
from django.db import models
from django.db.models import Count, FilteredRelation, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from .csv_export import safe_csv_writer
from .forms import MemberForm, MembershipTermForm
from .mixins import StaffRequiredMixin

STATUS_FILTERS = [("", "All members"), *MemberStatus.choices]


def this_month() -> tuple[int, int]:
    today = timezone.localdate()
    return today.year, today.month


def member_roster(request):
    """The roster as filtered by ?q= and ?status=.

    Status is derived from dates rather than stored, so the status filter
    runs in Python over the prefetched terms. The roster is a few hundred
    rows at most; a query that could express "expiring soon" in SQL would
    duplicate the definition that lives on the model.

    Reads from POST rather than GET on a POST request: the Redeem button
    is an hx-post that carries the roster filter form's fields via
    hx-include, so the swapped-back list stays filtered to whoever was on
    screen instead of reverting to the full roster.
    """
    params = request.POST if request.method == "POST" else request.GET
    first, last = month_bounds(*this_month())
    members = (
        Member.objects.prefetch_related("terms__tier").annotate(
            # The month goes in the JOIN's ON clause, so only this month's
            # redemptions are joined; a Count(filter=...) would join every
            # redemption ever recorded and discard most of them.
            redeemed_this_month=FilteredRelation(
                "free_admissions",
                condition=Q(free_admissions__redeemed_on__range=(first, last)),
            ),
            # distinct=True: this is the only multi-valued relation joined
            # into this query today, so it doesn't change the count — but it
            # makes the count immune to join fan-out if `?q=` ever matches a
            # multi-valued relation (e.g. terms__tier__name) or the status
            # filter moves into SQL, either of which would otherwise
            # silently multiply this count.
            free_used_this_month=Count("redeemed_this_month", distinct=True),
        )
        # Explicit: Django drops Meta.ordering from a GROUP BY query, and
        # the annotation above makes this one.
        .order_by("last_name", "first_name")  # Member.Meta.ordering
    )

    q = (params.get("q") or "").strip()
    if q:
        members = members.filter(
            models.Q(first_name__icontains=q)
            | models.Q(last_name__icontains=q)
            | models.Q(email__icontains=q)
        )

    status = (params.get("status") or "").strip()
    members = list(members)
    if status == MemberStatus.ACTIVE:
        # Covered today, expiring soon included: the same members as the
        # header's Member.objects.active() count. "Expiring soon" is a
        # narrower filter of its own, not a different kind of member.
        members = [m for m in members if m.is_active]
    elif status in MemberStatus.values:
        members = [m for m in members if m.status == status]
    return members, q, status


class MemberListView(StaffRequiredMixin, View):
    permission_required = "audience.view_member"

    def get(self, request):
        members, q, status = member_roster(request)

        first, last = month_bounds(*this_month())
        free_given_this_month = FreeAdmission.objects.filter(
            redeemed_on__range=(first, last)
        ).count()

        return render(
            request,
            "dashboard/members.html",
            {
                "members": members,
                "q": q,
                "selected_status": status,
                "statuses": STATUS_FILTERS,
                "active_count": Member.objects.active().count(),
                "free_given_this_month": free_given_this_month,
                "this_month_label": timezone.localdate().strftime("%B"),
            },
        )


def _render_member_form(request, form, action_url, submit_label):
    return render(
        request,
        "dashboard/_member_form.html",
        {"form": form, "form_action": action_url, "submit_label": submit_label},
    )


def _member_list_response(request, toast_message):
    """Success response: OOB-swap the list, close the drawer, and toast."""
    members, q, status = member_roster(request)
    html = render(
        request,
        "dashboard/_member_list.html",
        {"members": members},
    ).content.decode()
    html = html.replace(
        '<div id="member-list">', '<div id="member-list" hx-swap-oob="true">', 1
    )
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps(
        {
            "close-drawer": True,
            "dashboard-toast": {"kind": "success", "message": toast_message},
        }
    )
    return resp


class MemberCreateView(StaffRequiredMixin, View):
    permission_required = "audience.add_member"

    def get(self, request):
        return _render_member_form(
            request, MemberForm(), reverse("dashboard:member_create"), "Create Member"
        )

    def post(self, request):
        form = MemberForm(request.POST)
        if form.is_valid():
            form.save()
            return _member_list_response(request, "Member created")
        return _render_member_form(
            request, form, reverse("dashboard:member_create"), "Create Member"
        )


class MemberEditView(StaffRequiredMixin, View):
    permission_required = "audience.change_member"

    def get(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        return _render_member_form(
            request,
            MemberForm(instance=member),
            reverse("dashboard:member_edit", args=[pk]),
            "Save Changes",
        )

    def post(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        form = MemberForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            return _member_list_response(request, "Member updated")
        return _render_member_form(
            request,
            form,
            reverse("dashboard:member_edit", args=[pk]),
            "Save Changes",
        )


class MemberDeleteView(StaffRequiredMixin, View):
    permission_required = "audience.delete_member"

    def post(self, request, pk):
        # No ProtectedError guard, unlike Screens: a person entered by
        # mistake should be removable, and their terms only describe them.
        get_object_or_404(Member, pk=pk).delete()
        return _member_list_response(request, "Member deleted")


def _renewal_initial(member, request) -> dict:
    """Prefill for the Renew button: same tier, starting where the
    latest-running term leaves off.

    Only for `?renew=1` — a blank Add Term form still opens blank, because
    the reason to add a term by hand is usually that it is *not* a
    like-for-like renewal. Expiry and price are left out so the form fills
    them from the tier, which keeps a renewal honest about a price change
    since the last one.

    A retired tier is not prefilled: `MembershipTermForm` drops retired
    tiers from the dropdown for a new term, so the form opens on its empty
    "Choose a tier" option instead and staff must pick a replacement.
    """
    if request.GET.get("renew") != "1":
        return {}
    latest = latest_term(member.terms.select_related("tier"))
    if latest is None:
        return {}
    initial: dict[str, object] = {}
    # None for a term running to date.max: no day follows it, so staff
    # choose the start date themselves.
    started_on = renewal_start(latest, timezone.localdate())
    if started_on is not None:
        initial["started_on"] = started_on
    if latest.tier.show_on_membership_page:
        initial["tier"] = latest.tier_id
    return initial


def _render_term_form(request, form, action_url, submit_label):
    return render(
        request,
        "dashboard/_term_form.html",
        {"form": form, "form_action": action_url, "submit_label": submit_label},
    )


def _term_list_context(member) -> dict:
    """What `_term_list.html` needs, wherever it is rendered from.

    Re-reads the terms rather than trusting a prefetch on `member`: this
    runs right after a term was added, edited or deleted, and a prefetched
    cache from before the write would render the list the staffer just
    changed. The read becomes the member's prefetch, so the status pill
    and everything else on the page use these rows rather than querying
    again.
    """
    terms = member.reload_terms()
    return {
        "member": member,
        "terms": terms,
        "overlapping_term_ids": overlapping_term_ids(terms),
    }


def _term_list_response(request, member, toast_message):
    """OOB-swap the member's term list, close the drawer, and toast."""
    html = render(
        request,
        "dashboard/_term_list.html",
        _term_list_context(member),
    ).content.decode()
    html = html.replace(
        '<div id="term-list">', '<div id="term-list" hx-swap-oob="true">', 1
    )
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps(
        {
            "close-drawer": True,
            "dashboard-toast": {"kind": "success", "message": toast_message},
        }
    )
    return resp


class MemberDetailView(StaffRequiredMixin, View):
    permission_required = "audience.view_member"

    def get(self, request, pk):
        # Terms are read once, by _term_list_context below.
        member = get_object_or_404(
            Member.objects.prefetch_related(_admissions_with_recorder()), pk=pk
        )
        return render(
            request,
            "dashboard/member_detail.html",
            {
                **_term_list_context(member),
                "free_admission_months": _free_admission_months(member),
            },
        )


def _term_create_action(request, pk) -> tuple[str, str]:
    """The create form's post URL and submit label.

    A renewal keeps `?renew=1` on its post URL so an invalid submit
    re-renders as a renewal: the drawer is titled Renew Membership and the
    button should say so too.
    """
    url = reverse("dashboard:term_create", args=[pk])
    if request.GET.get("renew") == "1":
        return f"{url}?renew=1", "Renew Membership"
    return url, "Create Term"


class TermCreateView(StaffRequiredMixin, View):
    permission_required = "audience.add_membershipterm"

    def get(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        return _render_term_form(
            request,
            MembershipTermForm(initial=_renewal_initial(member, request)),
            *_term_create_action(request, pk),
        )

    def post(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        form = MembershipTermForm(request.POST)
        if form.is_valid():
            term = form.save(commit=False)
            # The member comes from the URL, never the payload.
            term.member = member
            term.save()
            renewed = request.GET.get("renew") == "1"
            return _term_list_response(
                request, member, "Membership renewed" if renewed else "Term created"
            )
        return _render_term_form(request, form, *_term_create_action(request, pk))


class TermEditView(StaffRequiredMixin, View):
    permission_required = "audience.change_membershipterm"

    def get(self, request, pk):
        term = get_object_or_404(MembershipTerm, pk=pk)
        return _render_term_form(
            request,
            MembershipTermForm(instance=term),
            reverse("dashboard:term_edit", args=[pk]),
            "Save Changes",
        )

    def post(self, request, pk):
        term = get_object_or_404(MembershipTerm, pk=pk)
        form = MembershipTermForm(request.POST, instance=term)
        if form.is_valid():
            # `member` is not a form field, so a posted member id is ignored.
            form.save()
            return _term_list_response(request, term.member, "Term updated")
        return _render_term_form(
            request,
            form,
            reverse("dashboard:term_edit", args=[pk]),
            "Save Changes",
        )


class TermDeleteView(StaffRequiredMixin, View):
    permission_required = "audience.delete_membershipterm"

    def post(self, request, pk):
        term = get_object_or_404(MembershipTerm, pk=pk)
        member = term.member
        term.delete()
        return _term_list_response(request, member, "Term deleted")


class MemberExportView(StaffRequiredMixin, View):
    """One row per member, from the term that runs latest.

    The same term Renew continues from, so the row's dates describe the
    cover that `status` is judged on rather than, say, a short comp that
    started more recently.

    Matches the shape of the spreadsheet this replaces. A per-term export
    for revenue analysis would be a second view; this one answers "who are
    my members".
    """

    permission_required = "audience.view_member"

    def get(self, request):
        members, _q, _status = member_roster(request)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="members.csv"'

        writer = safe_csv_writer(response)
        writer.writerow([
            "first_name", "last_name", "email", "phone",
            "tier", "started_on", "expires_on", "price_paid", "status",
        ])
        for member in members:
            term = latest_term(member.terms.all())
            writer.writerow([
                member.first_name,
                member.last_name,
                member.email,
                member.phone,
                term.tier.slug if term else "",
                term.started_on.isoformat() if term else "",
                term.expires_on.isoformat() if term else "",
                term.price_paid if term else "",
                member.status,
            ])
        return response


class FreeAdmissionRedeemView(StaffRequiredMixin, View):
    """Record one free admission for a member.

    Deliberately does not check the allowance. The screen warns before
    calling this when the member is already at their limit, and staff may
    go ahead — a two-screen cinema runs on the judgement of whoever is at
    the counter, and a server-side refusal would make the one legitimate
    override impossible.
    """

    permission_required = "audience.add_freeadmission"

    def post(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        FreeAdmission.objects.create(member=member, recorded_by=request.user)
        return _member_list_response(
            request, f"Free admission recorded for {member.full_name}"
        )


def _admissions_with_recorder() -> Prefetch:
    """A member's redemptions with who recorded each, which the panel
    prints on every row."""
    return Prefetch(
        "free_admissions", queryset=FreeAdmission.objects.select_related("recorded_by")
    )


def _free_admission_months(member):
    """This member's redemptions, newest month first.

    Grouped in Python over the prefetched rows rather than with a database
    aggregate: a member has a handful of these a year, and grouping here
    lets each month reuse `free_admissions_in` so the header count and the
    rows below it cannot disagree.

    Keyed by `(year, month)` rather than compared against the previous row,
    so the grouping is correct regardless of `FreeAdmission.Meta.ordering` —
    it does not depend on same-month rows being contiguous. Relies on
    Python dicts preserving insertion order, and on `member.free_admissions`
    yielding newest-first, to keep the months newest-first here too.
    """
    months: dict[tuple[int, int], dict] = {}
    for admission in member.free_admissions.all():
        key = (admission.redeemed_on.year, admission.redeemed_on.month)
        if key not in months:
            months[key] = {
                "key": key,
                "label": admission.redeemed_on.strftime("%B %Y"),
                "used": member.free_admissions_in(*key),
                "admissions": [],
            }
        months[key]["admissions"].append(admission)
    return list(months.values())


def _free_admission_list_response(request, member, toast_message):
    """Success response: OOB-swap the panel and toast."""
    member = Member.objects.prefetch_related(
        "terms__tier", _admissions_with_recorder()
    ).get(pk=member.pk)
    html = render(
        request,
        "dashboard/_free_admission_list.html",
        {"member": member, "free_admission_months": _free_admission_months(member)},
    ).content.decode()
    html = html.replace(
        '<div id="free-admission-list">',
        '<div id="free-admission-list" hx-swap-oob="true">',
        1,
    )
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps(
        {"dashboard-toast": {"kind": "success", "message": toast_message}}
    )
    return resp


class FreeAdmissionDeleteView(StaffRequiredMixin, View):
    permission_required = "audience.delete_freeadmission"

    def post(self, request, pk):
        admission = get_object_or_404(FreeAdmission, pk=pk)
        member = admission.member
        admission.delete()
        return _free_admission_list_response(
            request, member, "Free admission removed"
        )
