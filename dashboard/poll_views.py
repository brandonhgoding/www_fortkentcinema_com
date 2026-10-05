"""Staff surface for audience polls.

Separate from dashboard/views.py, which is already long and shares no
helpers with this feature.
"""

import json

from django.db.models import Max
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from cinema.models import (
    EmailPreference,
    Engagement,
    Film,
    Poll,
    PollOption,
    PollStatus,
)

from .csv_export import safe_csv_writer
from .forms import PollForm
from .mixins import StaffRequiredMixin


def _poll_list_response(request, toast_message: str) -> HttpResponse:
    """Success response for the poll drawer: swap the list out of band,
    close the drawer, and toast.

    The form posts into #drawer-content like every other drawer form, so an
    invalid submit re-renders the form in place. It used to target the
    list, which put the form with its errors where the table was and closed
    the drawer, since a 200 counts as a successful request.
    """
    response = render(
        request,
        "dashboard/_poll_list.html",
        {"polls": Poll.objects.all(), "oob": True},
    )
    response["HX-Trigger"] = json.dumps(
        {
            "close-drawer": True,
            "dashboard-toast": {"kind": "success", "message": toast_message},
        }
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
        return render(request, "dashboard/polls.html", {"polls": Poll.objects.all()})


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


class PollDeleteView(StaffRequiredMixin, View):
    """Delete a round outright, ballot and votes included.

    Options and votes cascade from the poll in the database, so one delete
    takes the whole round. The engagement a winner became is left alone: it
    is a booking in its own right, the poll only pointed at it.

    From the list the row's button is an htmx request, answered with the
    refreshed list. From the detail page there is nothing left to show, so a
    plain form posts here and is sent back to the list with a flash toast.
    """

    def post(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        title = poll.title
        poll.delete()
        if request.headers.get("HX-Request"):
            return _poll_list_response(request, f"Deleted {title}")
        messages.success(request, f"Deleted {title}")
        return redirect("dashboard:polls")


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


# The ballot's labels are the voter's own words; a table pill wants two.
EMAIL_PREFERENCE_SHORT = {
    EmailPreference.RESULTS: "Results only",
    EmailPreference.SUBSCRIBE: "Mailing list",
    EmailPreference.NONE: "No email",
}


class PollDetailView(StaffRequiredMixin, View):
    def get(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        counts = poll.contact_counts()
        return render(
            request,
            "dashboard/poll_detail.html",
            {
                "poll": poll,
                "tallies": poll.tallies(),
                "contact_rows": [
                    (EmailPreference(key).label, counts[key])
                    for key in EmailPreference.values
                ],
                "contactable_count": poll.contactable_votes().count(),
                # Newest first, the model's default, so a fresh vote is on top.
                "votes": poll.votes.select_related("option__film"),
                "preference_short": EMAIL_PREFERENCE_SHORT,
            },
        )


class PollVotesExportView(StaffRequiredMixin, View):
    """CSV of the voters we may write to, for telling them what won.

    Nothing in this project sends mail yet, so this export is how the
    "tell me the results" promise gets kept: close the round, download,
    send by hand. Voters who asked not to be emailed are not in it, and
    the preference column separates a one-off results note from the
    mailing list (whose members are also on the Subscribers page).
    """

    def get(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="poll-{poll.slug}-emails.csv"'
        )
        writer = safe_csv_writer(response)
        writer.writerow(["email", "preference", "film", "voted_at"])
        for vote in poll.contactable_votes().select_related("option__film"):
            writer.writerow(
                [
                    vote.email,
                    vote.email_preference,
                    vote.option.film.title,
                    vote.created_at.isoformat(),
                ]
            )
        return response


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

        film = Film.objects.filter(pk=_pk_or_none(request.POST.get("film_id"))).first()
        if film is None:
            return HttpResponseBadRequest("Unknown film.")

        if not poll.options.filter(film=film).exists():
            # Max, not count: after a removal the count repeats a taken slot.
            highest = poll.options.aggregate(m=Max("sort_order"))["m"] or 0
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
        index = next((i for i, opt in enumerate(options) if opt.pk == option_pk), None)
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


# The only moves the status buttons offer. Going back to DRAFT would unlock
# the ballot after votes are in (removing an option deletes its votes), and
# ANNOUNCED needs a winner, so it goes through PollAnnounceView.
_ALLOWED_MOVES = {
    PollStatus.DRAFT: {PollStatus.OPEN},
    PollStatus.OPEN: {PollStatus.CLOSED},
}


def _pk_or_none(raw):
    """An integer primary key from POST data, or None for blank or junk."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _poll_status_response(request, poll, toast_message: str = "") -> HttpResponse:
    response = render(request, "dashboard/_poll_status.html", {"poll": poll})
    if toast_message:
        response["HX-Trigger"] = json.dumps(
            {"dashboard-toast": {"kind": "success", "message": toast_message}}
        )
    return response


class PollStatusView(StaffRequiredMixin, View):
    """Move a round through draft -> open -> closed.

    Any number of rounds may be open at once; /vote lists them.
    """

    def post(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        status = request.POST.get("status")
        if status not in PollStatus.values:
            return HttpResponseBadRequest("Unknown status.")
        if status not in _ALLOWED_MOVES.get(poll.status, set()):
            return HttpResponse(
                f"A {poll.get_status_display().lower()} round can't be moved "
                f"to {PollStatus(status).label.lower()}.",
                status=409,
            )

        if status == PollStatus.OPEN:
            if not poll.options.exists():
                return HttpResponse(
                    "Add films to the ballot before opening the round.", status=409
                )

        poll.status = status
        poll.save(update_fields=["status"])
        return _poll_status_response(request, poll, f"Poll {status.lower()}")


class PollAnnounceView(StaffRequiredMixin, View):
    """Name the winner and, once booked, attach the engagement.

    The engagement link is what turns the public results page from
    "Casablanca won" into "Casablanca won, here are the showtimes".
    """

    def get(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        return render(
            request,
            "dashboard/_poll_announce.html",
            {
                "poll": poll,
                "tallies": poll.tallies(by_rank=True),
                "engagements": Engagement.objects.order_by("-start_date")[:20],
            },
        )

    def post(self, request, pk):
        poll = get_object_or_404(Poll, pk=pk)
        if poll.status not in (PollStatus.CLOSED, PollStatus.ANNOUNCED):
            return HttpResponse(
                "Close the round before announcing a winner.", status=409
            )

        winner = poll.options.filter(pk=_pk_or_none(request.POST.get("winner"))).first()
        if winner is None:
            return HttpResponseBadRequest("Unknown option.")

        poll.winner = winner
        poll.status = PollStatus.ANNOUNCED
        # "Not booked yet" posts a blank engagement and clears any old link.
        poll.engagement = Engagement.objects.filter(
            pk=_pk_or_none(request.POST.get("engagement"))
        ).first()

        poll.save(update_fields=["winner", "status", "engagement"])
        return _poll_status_response(request, poll, "Winner announced")
