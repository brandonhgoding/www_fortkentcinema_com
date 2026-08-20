"""Staff surface for audience polls.

Separate from dashboard/views.py, which is already long and shares no
helpers with this feature.
"""

import json

from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from cinema.models import Film, Poll, PollOption, PollStatus

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


def _poll_options_response(request, poll, toast_message: str = "") -> HttpResponse:
    response = render(
        request,
        "dashboard/_poll_options.html",
        {"poll": poll, "tallies": poll.tallies()},
    )
    if toast_message:
        response["HX-Trigger"] = json.dumps(
            {"dashboard-toast": {"kind": "success", "message": toast_message}}
        )
    return response


class PollDetailView(StaffRequiredMixin, View):
    def get(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        return render(
            request,
            "dashboard/poll_detail.html",
            {"poll": poll, "tallies": poll.tallies()},
        )


class PollOptionAddView(StaffRequiredMixin, View):
    """Add a film to a ballot.

    Refused once voting is open: changing the ballot mid-round would make the
    votes already cast meaningless.
    """

    def post(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        if poll.status != PollStatus.DRAFT:
            return HttpResponse(
                "The ballot is locked once a round leaves draft.", status=409
            )

        film = Film.objects.filter(pk=request.POST.get("film_id")).first()
        if film is None:
            return HttpResponseBadRequest("Unknown film.")

        if not poll.options.filter(film=film).exists():
            highest = poll.options.count()
            PollOption.objects.create(poll=poll, film=film, sort_order=highest + 1)

        return _poll_options_response(request, poll, f"Added {film.title}")


class PollOptionRemoveView(StaffRequiredMixin, View):
    def post(self, request, pk, option_pk):
        poll = get_object_or_404(Poll, pk=pk)
        if poll.status != PollStatus.DRAFT:
            return HttpResponse(
                "The ballot is locked once a round leaves draft.", status=409
            )
        poll.options.filter(pk=option_pk).delete()
        return _poll_options_response(request, poll, "Removed from ballot")


class PollOptionMoveView(StaffRequiredMixin, View):
    """Reorder the ballot by swapping an option with its neighbour.

    Ballot order is what visitors see top to bottom, so it is worth
    controlling. Locked once voting opens, like the rest of the ballot.
    """

    def post(self, request, pk, option_pk):
        poll = get_object_or_404(Poll, pk=pk)
        if poll.status != PollStatus.DRAFT:
            return HttpResponse(
                "The ballot is locked once a round leaves draft.", status=409
            )

        direction = request.POST.get("direction")
        if direction not in ("up", "down"):
            return HttpResponseBadRequest("Direction must be 'up' or 'down'.")

        options = list(poll.options.all())
        index = next(
            (i for i, opt in enumerate(options) if opt.pk == option_pk), None
        )
        if index is None:
            return HttpResponseBadRequest("Unknown option.")

        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(options):
            options[index], options[target] = options[target], options[index]
            # Renumber the whole ballot: sort_order values arrive from adds and
            # earlier swaps, so a bare pairwise swap can leave duplicates.
            for position, option in enumerate(options, start=1):
                if option.sort_order != position:
                    option.sort_order = position
                    option.save(update_fields=["sort_order"])

        return _poll_options_response(request, poll)
