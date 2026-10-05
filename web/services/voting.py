"""Resolves what the /vote page should show.

Six states, all of which must render: no poll, a choice between several
open rounds, an unvoted ballot, a cast ballot, a closed round awaiting a
decision, and an announced winner. This lives here rather than in the view
so each state is unit-testable without going through HTTP, matching the
cinema_data / showtimes convention.
"""

from django.db.models import Q, QuerySet
from django.utils import timezone

from cinema.models import Poll, PollStatus, Vote

STATE_NO_POLL = "no_poll"
STATE_CHOOSE = "choose"
STATE_BALLOT = "ballot"
STATE_VOTED = "voted"
STATE_CLOSED = "closed"
STATE_ANNOUNCED = "announced"

_DECIDED = (PollStatus.CLOSED, PollStatus.ANNOUNCED)


def _finished_q(now) -> Q:
    """Rounds that are done taking votes: decided by staff, or still OPEN
    but past their closes_at."""
    return Q(status__in=_DECIDED) | (Q(status=PollStatus.OPEN) & Poll.ended_q(now))


def open_polls() -> list[Poll]:
    """Every round taking votes right now, newest first.

    Several may be open at once; the callers decide whether to show one
    ballot or a list.
    """
    now = timezone.now()
    return list(
        Poll.objects.filter(status=PollStatus.OPEN)
        .filter(Poll.started_q(now))
        .exclude(Poll.ended_q(now))
        .select_related("winner", "engagement")
    )


def latest_decided_poll() -> Poll | None:
    """The most recent round that has finished voting.

    Announced rounds outrank merely-closed ones, so a freshly closed round
    does not bury the winner people are still looking for.
    """
    announced = (
        Poll.objects.filter(status=PollStatus.ANNOUNCED)
        .select_related("winner", "winner__film", "engagement")
        .first()
    )
    if announced is not None:
        return announced
    return (
        Poll.objects.filter(_finished_q(timezone.now()))
        .exclude(status=PollStatus.ANNOUNCED)
        .select_related("winner", "winner__film", "engagement")
        .first()
    )


def archived_polls() -> QuerySet:
    """Past rounds, newest first. There is no separate archive index page —
    /vote lists these and each links to its own /vote/<slug>."""
    return Poll.objects.filter(_finished_q(timezone.now())).select_related(
        "winner", "winner__film"
    )


def resolve_vote_page(poll: Poll | None = None, vote: Vote | None = None) -> dict:
    """Build the context for /vote or /vote/<slug>.

    `poll` pins the page to a specific round (its own /vote/<slug> page, or
    the round a ballot was just cast in). Without it: one open round shows
    its ballot, several show a list to pick from, and none falls back to
    the most recent decided round.

    `vote` is the ballot just cast, for the response to a submission. There
    is no cookie, so a plain visit cannot tell who is looking: an open round
    always shows the ballot, and a repeat address is caught on submit.
    """
    open_rounds: list[Poll] = []
    if poll is None:
        open_rounds = open_polls()
        if len(open_rounds) == 1:
            poll = open_rounds[0]
        elif not open_rounds:
            poll = latest_decided_poll()

    archive = archived_polls()
    if poll is not None:
        archive = archive.exclude(pk=poll.pk)

    ctx = {
        "state": STATE_NO_POLL,
        "poll": poll,
        "open_rounds": open_rounds,
        "options": [],
        "tallies": [],
        "show_results": False,
        "voted_option": None,
        "vote": None,
        "archive": archive,
    }

    if poll is None:
        if len(open_rounds) > 1:
            ctx["state"] = STATE_CHOOSE
        return ctx

    ctx["options"] = list(poll.options.select_related("film"))

    if poll.status == PollStatus.ANNOUNCED:
        ctx["state"] = STATE_ANNOUNCED
        ctx["show_results"] = True
        ctx["tallies"] = poll.tallies(by_rank=True)
        return ctx

    if poll.status == PollStatus.CLOSED or (
        poll.status == PollStatus.OPEN and poll.has_ended()
    ):
        ctx["state"] = STATE_CLOSED
        ctx["show_results"] = poll.results_visible
        if poll.results_visible:
            ctx["tallies"] = poll.tallies(by_rank=True)
        return ctx

    if poll.status != PollStatus.OPEN or not poll.has_started():
        # A draft round, or one whose window has not opened, is not public.
        # Treat it as no poll at all.
        ctx["poll"] = None
        ctx["options"] = []
        return ctx

    if vote is None or vote.poll_id != poll.pk:
        ctx["state"] = STATE_BALLOT
        return ctx

    ctx["state"] = STATE_VOTED
    ctx["voted_option"] = vote.option
    ctx["vote"] = vote
    ctx["show_results"] = poll.results_visible
    if poll.results_visible:
        ctx["tallies"] = poll.tallies(by_rank=True)
    return ctx
