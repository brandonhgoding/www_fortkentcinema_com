"""Staff surface for audience polls.

Separate from dashboard/views.py, which is already long and shares no
helpers with this feature.
"""

import json

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from cinema.models import Poll

from .forms import PollForm
from .mixins import StaffRequiredMixin


def _poll_list_response(request, toast_message: str = "") -> HttpResponse:
    response = render(
        request,
        "dashboard/_poll_list.html",
        {"polls": Poll.objects.all()},
    )
    if toast_message:
        response["HX-Trigger"] = json.dumps(
            {"dashboard-toast": {"kind": "success", "message": toast_message}}
        )
    return response


def _render_poll_form(request, form, action_url: str, submit_label: str):
    return render(
        request,
        "dashboard/_poll_form.html",
        {"form": form, "action_url": action_url, "submit_label": submit_label},
    )


class PollListView(StaffRequiredMixin, View):
    def get(self, request):
        return render(
            request, "dashboard/polls.html", {"polls": Poll.objects.all()}
        )


class PollCreateView(StaffRequiredMixin, View):
    def get(self, request):
        return _render_poll_form(
            request, PollForm(), reverse("dashboard:poll_create"), "Create Poll"
        )

    def post(self, request):
        form = PollForm(request.POST)
        if form.is_valid():
            form.save()
            return _poll_list_response(request, "Poll created")
        return _render_poll_form(
            request, form, reverse("dashboard:poll_create"), "Create Poll"
        )


class PollEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        return _render_poll_form(
            request,
            PollForm(instance=poll),
            reverse("dashboard:poll_edit", args=[pk]),
            "Save Changes",
        )

    def post(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        form = PollForm(request.POST, instance=poll)
        if form.is_valid():
            form.save()
            return _poll_list_response(request, "Poll updated")
        return _render_poll_form(
            request,
            form,
            reverse("dashboard:poll_edit", args=[pk]),
            "Save Changes",
        )
