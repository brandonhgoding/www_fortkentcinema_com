import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

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


class PollWindowTests(TestCase):
    def test_closes_before_opens_is_invalid(self) -> None:
        now = timezone.now()
        poll = Poll(
            title="Backwards", opens_at=now, closes_at=now - datetime.timedelta(1)
        )
        with self.assertRaises(ValidationError) as caught:
            poll.full_clean()
        self.assertIn("closes_at", caught.exception.message_dict)

    def test_open_poll_with_no_window_accepts_votes(self) -> None:
        poll = Poll(title="Live", status=PollStatus.OPEN)
        self.assertTrue(poll.is_accepting_votes())


class OneOpenPollTests(TestCase):
    def test_several_polls_may_be_open_at_once(self) -> None:
        Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        Poll.objects.create(title="Round Two", status=PollStatus.OPEN)
        self.assertEqual(Poll.objects.filter(status=PollStatus.OPEN).count(), 2)

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

    def test_one_vote_per_email_per_poll(self) -> None:
        Vote.objects.create(poll=self.poll, option=self.option, email="a@example.com")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Vote.objects.create(
                    poll=self.poll, option=self.option, email="A@Example.com"
                )

    def test_same_email_may_vote_in_a_different_poll(self) -> None:
        other_poll = Poll.objects.create(title="Round Two")
        other_option = PollOption.objects.create(
            poll=other_poll, film=Film.objects.create(title="The Thing")
        )
        Vote.objects.create(poll=self.poll, option=self.option, email="a@example.com")
        Vote.objects.create(poll=other_poll, option=other_option, email="a@example.com")
        self.assertEqual(Vote.objects.filter(email="a@example.com").count(), 2)

    def test_legacy_votes_without_an_email_do_not_collide(self) -> None:
        Vote.objects.create(poll=self.poll, option=self.option)
        Vote.objects.create(poll=self.poll, option=self.option)
        self.assertEqual(Vote.objects.filter(email="").count(), 2)


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
            Vote.objects.create(poll=self.poll, option=self.a, email=f"{key}@x.com")
        Vote.objects.create(poll=self.poll, option=self.b, email="k4@x.com")

        tallies = self.poll.tallies()

        self.assertEqual(self.poll.total_votes, 4)
        self.assertEqual(tallies[0]["option"], self.a)
        self.assertEqual(tallies[0]["count"], 3)
        self.assertEqual(tallies[0]["percent"], 75)
        self.assertEqual(tallies[1]["count"], 1)
        self.assertEqual(tallies[1]["percent"], 25)

    def test_tallies_are_sorted_by_count_when_asked(self) -> None:
        Vote.objects.create(poll=self.poll, option=self.b, email="k1@x.com")
        tallies = self.poll.tallies(by_rank=True)
        self.assertEqual(tallies[0]["option"], self.b)
