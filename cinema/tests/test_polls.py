from django.db import IntegrityError, transaction
from django.test import TestCase

from cinema.models import Film, Poll, PollOption, PollStatus, Vote


class PollSlugTests(TestCase):
    def test_slug_generated_from_title(self) -> None:
        poll = Poll.objects.create(title="Pick Our October Classic")
        self.assertEqual(poll.slug, "pick-our-october-classic")

    def test_duplicate_titles_get_suffixed_slugs(self) -> None:
        first = Poll.objects.create(title="Halloween Vote")
        second = Poll.objects.create(title="Halloween Vote")
        self.assertEqual(first.slug, "halloween-vote")
        self.assertEqual(second.slug, "halloween-vote-2")


class OneOpenPollTests(TestCase):
    def test_second_open_poll_is_refused_by_the_database(self) -> None:
        Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Poll.objects.create(title="Round Two", status=PollStatus.OPEN)

    def test_many_closed_polls_are_fine(self) -> None:
        Poll.objects.create(title="Round One", status=PollStatus.CLOSED)
        Poll.objects.create(title="Round Two", status=PollStatus.CLOSED)
        self.assertEqual(Poll.objects.filter(status=PollStatus.CLOSED).count(), 2)


class PollOptionTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.film = Film.objects.create(title="Casablanca")

    def test_a_film_can_only_appear_once_per_poll(self) -> None:
        PollOption.objects.create(poll=self.poll, film=self.film)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PollOption.objects.create(poll=self.poll, film=self.film)

    def test_options_order_by_sort_order(self) -> None:
        other = Film.objects.create(title="The Thing")
        second = PollOption.objects.create(poll=self.poll, film=self.film, sort_order=2)
        first = PollOption.objects.create(poll=self.poll, film=other, sort_order=1)
        self.assertEqual(list(self.poll.options.all()), [first, second])


class VoteConstraintTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )

    def test_one_vote_per_voter_key_per_poll(self) -> None:
        Vote.objects.create(poll=self.poll, option=self.option, voter_key="abc")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Vote.objects.create(poll=self.poll, option=self.option, voter_key="abc")

    def test_same_voter_key_may_vote_in_a_different_poll(self) -> None:
        other_poll = Poll.objects.create(title="Round Two")
        other_option = PollOption.objects.create(
            poll=other_poll, film=Film.objects.create(title="The Thing")
        )
        Vote.objects.create(poll=self.poll, option=self.option, voter_key="abc")
        Vote.objects.create(poll=other_poll, option=other_option, voter_key="abc")
        self.assertEqual(Vote.objects.filter(voter_key="abc").count(), 2)


class PollTallyTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.a = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca"), sort_order=1
        )
        self.b = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="The Thing"), sort_order=2
        )

    def test_tallies_with_no_votes_are_zero_not_a_crash(self) -> None:
        tallies = self.poll.tallies()
        self.assertEqual([t["count"] for t in tallies], [0, 0])
        self.assertEqual([t["percent"] for t in tallies], [0, 0])
        self.assertEqual(self.poll.total_votes, 0)

    def test_tallies_count_and_percent(self) -> None:
        for key in ("k1", "k2", "k3"):
            Vote.objects.create(poll=self.poll, option=self.a, voter_key=key)
        Vote.objects.create(poll=self.poll, option=self.b, voter_key="k4")

        tallies = self.poll.tallies()

        self.assertEqual(self.poll.total_votes, 4)
        self.assertEqual(tallies[0]["option"], self.a)
        self.assertEqual(tallies[0]["count"], 3)
        self.assertEqual(tallies[0]["percent"], 75)
        self.assertEqual(tallies[1]["count"], 1)
        self.assertEqual(tallies[1]["percent"], 25)

    def test_tallies_are_sorted_by_count_when_asked(self) -> None:
        Vote.objects.create(poll=self.poll, option=self.b, voter_key="k1")
        tallies = self.poll.tallies(by_rank=True)
        self.assertEqual(tallies[0]["option"], self.b)
