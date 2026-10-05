import datetime

from django.test import RequestFactory, TestCase
from django.utils import timezone

from cinema import voting
from cinema.models import Film, Poll, PollOption, PollStatus, Vote


class ClientIPTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_prefers_first_forwarded_hop(self) -> None:
        request = self.factory.get(
            "/vote", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1"
        )
        self.assertEqual(voting.client_ip(request), "203.0.113.9")

    def test_falls_back_to_remote_addr(self) -> None:
        request = self.factory.get("/vote", REMOTE_ADDR="198.51.100.4")
        self.assertEqual(voting.client_ip(request), "198.51.100.4")

    def test_malformed_forwarded_header_returns_none(self) -> None:
        # A spoofed/garbage header must never reach an `inet` column, which
        # rejects non-IP text outright.
        request = self.factory.get("/vote", HTTP_X_FORWARDED_FOR="not-an-ip")
        self.assertIsNone(voting.client_ip(request))

    def test_malformed_forwarded_header_does_not_fall_back_to_remote_addr(
        self,
    ) -> None:
        # The header branch is taken and rejected outright — a bad header
        # does not silently defer to a perfectly good REMOTE_ADDR.
        request = self.factory.get(
            "/vote",
            HTTP_X_FORWARDED_FOR="not-an-ip",
            REMOTE_ADDR="198.51.100.4",
        )
        self.assertIsNone(voting.client_ip(request))

    def test_ipv6_forwarded_address_is_accepted(self) -> None:
        request = self.factory.get(
            "/vote", HTTP_X_FORWARDED_FOR="2001:db8::1"
        )
        self.assertEqual(voting.client_ip(request), "2001:db8::1")


class CastVoteTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )
        self.other = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="The Thing")
        )

    def test_records_a_vote(self) -> None:
        vote = voting.cast_vote(self.poll, self.option, "k1")
        self.assertEqual(Vote.objects.count(), 1)
        self.assertEqual(vote.option, self.option)

    def test_second_vote_from_same_key_raises_already_voted(self) -> None:
        voting.cast_vote(self.poll, self.option, "k1")
        with self.assertRaises(voting.AlreadyVoted):
            voting.cast_vote(self.poll, self.other, "k1")
        self.assertEqual(Vote.objects.count(), 1)

    def test_closed_poll_refuses_the_write(self) -> None:
        self.poll.status = PollStatus.CLOSED
        self.poll.save()
        with self.assertRaises(voting.PollNotOpen):
            voting.cast_vote(self.poll, self.option, "k1")
        self.assertEqual(Vote.objects.count(), 0)

    def test_draft_poll_refuses_the_write(self) -> None:
        self.poll.status = PollStatus.DRAFT
        self.poll.save()
        with self.assertRaises(voting.PollNotOpen):
            voting.cast_vote(self.poll, self.option, "k1")

    def test_option_from_another_poll_is_refused(self) -> None:
        stray_poll = Poll.objects.create(title="Round Two")
        stray = PollOption.objects.create(
            poll=stray_poll, film=Film.objects.create(title="Alien")
        )
        with self.assertRaises(voting.OptionMismatch):
            voting.cast_vote(self.poll, stray, "k1")

    def test_poll_past_its_closes_at_refuses_the_write(self) -> None:
        self.poll.closes_at = timezone.now() - datetime.timedelta(minutes=1)
        self.poll.save()
        with self.assertRaises(voting.PollNotOpen):
            voting.cast_vote(self.poll, self.option, "k1")
        self.assertEqual(Vote.objects.count(), 0)

    def test_poll_before_its_opens_at_refuses_the_write(self) -> None:
        self.poll.opens_at = timezone.now() + datetime.timedelta(hours=1)
        self.poll.save()
        with self.assertRaises(voting.PollNotOpen):
            voting.cast_vote(self.poll, self.option, "k1")

    def test_poll_inside_its_window_records_the_vote(self) -> None:
        now = timezone.now()
        self.poll.opens_at = now - datetime.timedelta(hours=1)
        self.poll.closes_at = now + datetime.timedelta(hours=1)
        self.poll.save()
        voting.cast_vote(self.poll, self.option, "k1")
        self.assertEqual(Vote.objects.count(), 1)

    def test_many_voters_behind_one_address_all_count(self) -> None:
        for i in range(10):
            voting.cast_vote(self.poll, self.option, f"k{i}")
        self.assertEqual(Vote.objects.count(), 10)
