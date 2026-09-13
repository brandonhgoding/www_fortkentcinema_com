"""Staff surface for the membership roster.

Replaces a spreadsheet. Memberships are still sold through Square payment
links; nothing here talks to Square, and nothing here is public — members
are the first real customer PII in this database, so every view is
staff-only, the CSV export included.
"""

import csv
import json

from audience.models import Member, MembershipTerm
from django.db import models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from .forms import MemberForm, MembershipTermForm
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
                "active_count": Member.objects.active().count(),
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
    def get(self, request):
        return _render_member_form(
            request, MemberForm(), reverse("dashboard:member_create"), "Add Member"
        )

    def post(self, request):
        form = MemberForm(request.POST)
        if form.is_valid():
            form.save()
            return _member_list_response(request, "Member added")
        return _render_member_form(
            request, form, reverse("dashboard:member_create"), "Add Member"
        )


class MemberEditView(StaffRequiredMixin, View):
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
    def post(self, request, pk):
        # No ProtectedError guard, unlike Screens: a person entered by
        # mistake should be removable, and their terms only describe them.
        get_object_or_404(Member, pk=pk).delete()
        return _member_list_response(request, "Member deleted")


def _render_term_form(request, form, action_url, submit_label):
    return render(
        request,
        "dashboard/_term_form.html",
        {"form": form, "form_action": action_url, "submit_label": submit_label},
    )


def _term_list_response(request, member, toast_message):
    """OOB-swap the member's term list, close the drawer, and toast."""
    html = render(
        request,
        "dashboard/_term_list.html",
        {
            "member": member,
            "terms": member.terms.all(),
        },
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
    def get(self, request, pk):
        member = get_object_or_404(
            Member.objects.prefetch_related("terms"), pk=pk
        )
        return render(
            request,
            "dashboard/member_detail.html",
            {
                "member": member,
                "terms": member.terms.all(),
            },
        )


class TermCreateView(StaffRequiredMixin, View):
    def get(self, request, pk):
        get_object_or_404(Member, pk=pk)
        return _render_term_form(
            request,
            MembershipTermForm(),
            reverse("dashboard:term_create", args=[pk]),
            "Add Term",
        )

    def post(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        form = MembershipTermForm(request.POST)
        if form.is_valid():
            term = form.save(commit=False)
            # The member comes from the URL, never the payload.
            term.member = member
            term.save()
            return _term_list_response(request, member, "Term added")
        return _render_term_form(
            request,
            form,
            reverse("dashboard:term_create", args=[pk]),
            "Add Term",
        )


class TermEditView(StaffRequiredMixin, View):
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
    def post(self, request, pk):
        term = get_object_or_404(MembershipTerm, pk=pk)
        member = term.member
        term.delete()
        return _term_list_response(request, member, "Term deleted")


class MemberExportView(StaffRequiredMixin, View):
    """One row per member, from their most recent term.

    Matches the shape of the spreadsheet this replaces. A per-term export
    for revenue analysis would be a second view; this one answers "who are
    my members".
    """

    def get(self, request):
        members, _q, _status = member_roster(request)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="members.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "first_name", "last_name", "email", "phone",
            "tier", "started_on", "expires_on", "price_paid", "status",
        ])
        for member in members:
            term = member.terms.first()  # ordering is -started_on
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
