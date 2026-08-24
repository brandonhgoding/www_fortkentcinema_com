from django.test import RequestFactory, TestCase

from cinema import voting
from cinema.models import Film, Poll, PollOption, PollStatus, Vote


class HashIPTests(TestCase):
    def test_hash_is_stable_and_not_the_raw_address(self) -> None:
        first = voting.hash_ip("10.0.0.1")
        second = voting.hash_ip("10.0.0.1")
        self.assertEqual(first, second)
        self.assertNotIn("10.0.0.1", first)
        self.assertEqual(len(first), 64)

    def test_different_addresses_hash_differently(self) -> None:
        self.assertNotEqual(voting.hash_ip("10.0.0.1"), voting.hash_ip("10.0.0.2"))

    def test_missing_ip_hashes_to_empty_string(self) -> None:
        self.assertEqual(voting.hash_ip(None), "")


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
        vote = voting.cast_vote(self.poll, self.option, "k1", ip="10.0.0.1")
        self.assertEqual(Vote.objects.count(), 1)
        self.assertEqual(vote.option, self.option)
        self.assertEqual(vote.ip_hash, voting.hash_ip("10.0.0.1"))
        self.assertNotEqual(vote.ip_hash, "10.0.0.1")

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

    def test_ip_cap_stops_the_sixth_vote_from_one_address(self) -> None:
        for i in range(voting.IP_VOTE_CAP):
            voting.cast_vote(self.poll, self.option, f"k{i}", ip="10.0.0.1")
        with self.assertRaises(voting.IPCapReached):
            voting.cast_vote(self.poll, self.option, "k-last", ip="10.0.0.1")
        self.assertEqual(Vote.objects.count(), voting.IP_VOTE_CAP)

    def test_ip_cap_is_per_poll(self) -> None:
        for i in range(voting.IP_VOTE_CAP):
            voting.cast_vote(self.poll, self.option, f"k{i}", ip="10.0.0.1")
        self.poll.status = PollStatus.CLOSED
        self.poll.save()

        next_poll = Poll.objects.create(title="Round Two", status=PollStatus.OPEN)
        next_option = PollOption.objects.create(
            poll=next_poll, film=Film.objects.create(title="Jaws")
        )
        vote = voting.cast_vote(next_poll, next_option, "k0", ip="10.0.0.1")
        self.assertIsNotNone(vote.pk)

    def test_votes_without_an_ip_are_not_capped(self) -> None:
        for i in range(voting.IP_VOTE_CAP + 2):
            voting.cast_vote(self.poll, self.option, f"k{i}")
        self.assertEqual(Vote.objects.count(), voting.IP_VOTE_CAP + 2)


class ExistingVoteTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )

    def test_returns_none_without_a_key(self) -> None:
        self.assertIsNone(voting.existing_vote(self.poll, None))

    def test_returns_the_vote_when_present(self) -> None:
        voting.cast_vote(self.poll, self.option, "k1")
        found = voting.existing_vote(self.poll, "k1")
        self.assertIsNotNone(found)
        self.assertEqual(found.option, self.option)
