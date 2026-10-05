import datetime

from django.test import TestCase
from django.utils import timezone

from cinema import voting
from cinema.models import Film, Poll, PollOption, PollStatus
from web.services import voting as vote_service


class CurrentPollTests(TestCase):
    def test_none_when_nothing_is_open(self) -> None:
        Poll.objects.create(title="Old", status=PollStatus.CLOSED)
        self.assertIsNone(vote_service.current_poll())

    def test_returns_the_open_poll(self) -> None:
        poll = Poll.objects.create(title="Live", status=PollStatus.OPEN)
        self.assertEqual(vote_service.current_poll(), poll)

    def test_none_when_the_open_poll_is_past_its_closes_at(self) -> None:
        Poll.objects.create(
            title="Lapsed",
            status=PollStatus.OPEN,
            closes_at=timezone.now() - datetime.timedelta(minutes=1),
        )
        self.assertIsNone(vote_service.current_poll())

    def test_none_when_the_open_poll_has_not_opened_yet(self) -> None:
        Poll.objects.create(
            title="Soon",
            status=PollStatus.OPEN,
            opens_at=timezone.now() + datetime.timedelta(hours=1),
        )
        self.assertIsNone(vote_service.current_poll())


class ArchiveTests(TestCase):
    def test_archive_holds_closed_and_announced_only(self) -> None:
        Poll.objects.create(title="Draft", status=PollStatus.DRAFT)
        Poll.objects.create(title="Live", status=PollStatus.OPEN)
        closed = Poll.objects.create(title="Closed", status=PollStatus.CLOSED)
        announced = Poll.objects.create(title="Done", status=PollStatus.ANNOUNCED)

        archive = list(vote_service.archived_polls())

        self.assertIn(closed, archive)
        self.assertIn(announced, archive)
        self.assertEqual(len(archive), 2)

    def test_latest_decided_prefers_announced(self) -> None:
        Poll.objects.create(title="Closed", status=PollStatus.CLOSED)
        announced = Poll.objects.create(title="Done", status=PollStatus.ANNOUNCED)
        self.assertEqual(vote_service.latest_decided_poll(), announced)


class LapsedPollTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(
            title="Lapsed",
            status=PollStatus.OPEN,
            results_visible=True,
            closes_at=timezone.now() - datetime.timedelta(minutes=1),
        )
        PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )

    def test_vote_page_shows_it_as_closed(self) -> None:
        ctx = vote_service.resolve_vote_page(voter_key=None)
        self.assertEqual(ctx["poll"], self.poll)
        self.assertEqual(ctx["state"], vote_service.STATE_CLOSED)
        self.assertTrue(ctx["show_results"])

    def test_an_announced_round_still_outranks_it(self) -> None:
        announced = Poll.objects.create(title="Done", status=PollStatus.ANNOUNCED)
        self.assertEqual(vote_service.latest_decided_poll(), announced)
        self.assertIn(self.poll, vote_service.archived_polls())


class ResolveVotePageTests(TestCase):
    def _open_poll_with_options(self) -> Poll:
        poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        PollOption.objects.create(
            poll=poll, film=Film.objects.create(title="Casablanca"), sort_order=1
        )
        PollOption.objects.create(
            poll=poll, film=Film.objects.create(title="The Thing"), sort_order=2
        )
        return poll

    def test_no_poll_state(self) -> None:
        ctx = vote_service.resolve_vote_page(voter_key=None)
        self.assertEqual(ctx["state"], vote_service.STATE_NO_POLL)
        self.assertIsNone(ctx["poll"])

    def test_ballot_state_for_a_fresh_visitor(self) -> None:
        poll = self._open_poll_with_options()
        ctx = vote_service.resolve_vote_page(voter_key="never-voted")
        self.assertEqual(ctx["state"], vote_service.STATE_BALLOT)
        self.assertEqual(ctx["poll"], poll)
        self.assertEqual(len(ctx["options"]), 2)
        self.assertIsNone(ctx["voted_option"])

    def test_voted_state_after_casting(self) -> None:
        poll = self._open_poll_with_options()
        option = poll.options.first()
        voting.cast_vote(poll, option, "k1")

        ctx = vote_service.resolve_vote_page(voter_key="k1")

        self.assertEqual(ctx["state"], vote_service.STATE_VOTED)
        self.assertEqual(ctx["voted_option"], option)
        self.assertTrue(ctx["show_results"])
        self.assertEqual(sum(t["count"] for t in ctx["tallies"]), 1)

    def test_results_hidden_when_poll_says_so(self) -> None:
        poll = self._open_poll_with_options()
        poll.results_visible = False
        poll.save()
        voting.cast_vote(poll, poll.options.first(), "k1")

        ctx = vote_service.resolve_vote_page(voter_key="k1")

        self.assertEqual(ctx["state"], vote_service.STATE_VOTED)
        self.assertFalse(ctx["show_results"])

    def test_closed_state_falls_back_to_the_last_round(self) -> None:
        poll = self._open_poll_with_options()
        poll.status = PollStatus.CLOSED
        poll.save()

        ctx = vote_service.resolve_vote_page(voter_key=None)

        self.assertEqual(ctx["state"], vote_service.STATE_CLOSED)
        self.assertEqual(ctx["poll"], poll)

    def test_announced_state_exposes_the_winner(self) -> None:
        poll = self._open_poll_with_options()
        winner = poll.options.first()
        poll.winner = winner
        poll.status = PollStatus.ANNOUNCED
        poll.save()

        ctx = vote_service.resolve_vote_page(voter_key=None)

        self.assertEqual(ctx["state"], vote_service.STATE_ANNOUNCED)
        self.assertEqual(ctx["poll"].winner, winner)
        self.assertTrue(ctx["show_results"])

    def test_an_explicit_poll_overrides_the_current_one(self) -> None:
        self._open_poll_with_options()
        archived = Poll.objects.create(title="Old", status=PollStatus.CLOSED)

        ctx = vote_service.resolve_vote_page(voter_key=None, poll=archived)

        self.assertEqual(ctx["poll"], archived)
        self.assertEqual(ctx["state"], vote_service.STATE_CLOSED)

    def test_archive_excludes_the_poll_being_shown(self) -> None:
        shown = Poll.objects.create(title="Shown", status=PollStatus.ANNOUNCED)
        other = Poll.objects.create(title="Other", status=PollStatus.CLOSED)

        ctx = vote_service.resolve_vote_page(voter_key=None, poll=shown)

        self.assertNotIn(shown, ctx["archive"])
        self.assertIn(other, ctx["archive"])
