from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cinema.models import (
    Engagement,
    Film,
    Poll,
    PollOption,
    PollStatus,
    Screen,
    Vote,
)

User = get_user_model()


class PollStatusTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.poll = Poll.objects.create(title="Round One")
        PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )

    def test_open_a_draft(self) -> None:
        self.client.post(
            reverse("dashboard:poll_status", args=[self.poll.pk]),
            {"status": PollStatus.OPEN},
        )
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.status, PollStatus.OPEN)

    def test_cannot_open_a_ballotless_poll(self) -> None:
        empty = Poll.objects.create(title="Empty")
        response = self.client.post(
            reverse("dashboard:poll_status", args=[empty.pk]),
            {"status": PollStatus.OPEN},
        )
        self.assertEqual(response.status_code, 409)
        empty.refresh_from_db()
        self.assertEqual(empty.status, PollStatus.DRAFT)

    def test_second_open_poll_is_refused_with_a_message(self) -> None:
        self.poll.status = PollStatus.OPEN
        self.poll.save()
        other = Poll.objects.create(title="Round Two")
        PollOption.objects.create(
            poll=other, film=Film.objects.create(title="The Thing")
        )

        response = self.client.post(
            reverse("dashboard:poll_status", args=[other.pk]),
            {"status": PollStatus.OPEN},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("already open", response.content.decode().lower())
        other.refresh_from_db()
        self.assertEqual(other.status, PollStatus.DRAFT)

    def test_close_an_open_poll(self) -> None:
        self.poll.status = PollStatus.OPEN
        self.poll.save()
        self.client.post(
            reverse("dashboard:poll_status", args=[self.poll.pk]),
            {"status": PollStatus.CLOSED},
        )
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.status, PollStatus.CLOSED)

    def test_unknown_status_is_a_bad_request(self) -> None:
        response = self.client.post(
            reverse("dashboard:poll_status", args=[self.poll.pk]),
            {"status": "BOGUS"},
        )
        self.assertEqual(response.status_code, 400)

    def test_requires_staff(self) -> None:
        self.client.logout()
        response = self.client.post(
            reverse("dashboard:poll_status", args=[self.poll.pk]),
            {"status": PollStatus.OPEN},
        )
        self.assertEqual(response.status_code, 302)


class PollAnnounceTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.CLOSED)
        self.leader = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )
        self.runner_up = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="The Thing")
        )
        Vote.objects.create(poll=self.poll, option=self.leader, voter_key="k1")
        Vote.objects.create(poll=self.poll, option=self.leader, voter_key="k2")
        Vote.objects.create(poll=self.poll, option=self.runner_up, voter_key="k3")

    def test_announce_form_defaults_to_the_leader(self) -> None:
        html = self.client.get(
            reverse("dashboard:poll_announce", args=[self.poll.pk])
        ).content.decode()
        self.assertIn(f'value="{self.leader.pk}" checked', html)

    def test_announce_sets_winner_and_status(self) -> None:
        self.client.post(
            reverse("dashboard:poll_announce", args=[self.poll.pk]),
            {"winner": self.leader.pk},
        )
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.winner, self.leader)
        self.assertEqual(self.poll.status, PollStatus.ANNOUNCED)

    def test_the_leader_can_be_overridden(self) -> None:
        self.client.post(
            reverse("dashboard:poll_announce", args=[self.poll.pk]),
            {"winner": self.runner_up.pk},
        )
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.winner, self.runner_up)

    def test_an_engagement_can_be_attached(self) -> None:
        screen = Screen.objects.create(
            name="Screen 1", capacity=100, screen_type="standard",
            aspect_ratio="flat", sound_system="standard", supports_3d=False,
        )
        engagement = Engagement.objects.create(
            screen=screen, start_date="2026-10-01", end_date="2026-10-03"
        )
        self.client.post(
            reverse("dashboard:poll_announce", args=[self.poll.pk]),
            {"winner": self.leader.pk, "engagement": engagement.pk},
        )
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.engagement, engagement)

    def test_cannot_announce_an_open_poll(self) -> None:
        open_poll = Poll.objects.create(title="Live", status=PollStatus.OPEN)
        option = PollOption.objects.create(
            poll=open_poll, film=Film.objects.create(title="Alien")
        )
        response = self.client.post(
            reverse("dashboard:poll_announce", args=[open_poll.pk]),
            {"winner": option.pk},
        )
        self.assertEqual(response.status_code, 409)

    def test_a_winner_from_another_poll_is_refused(self) -> None:
        stray_poll = Poll.objects.create(title="Other")
        stray = PollOption.objects.create(
            poll=stray_poll, film=Film.objects.create(title="Alien")
        )
        response = self.client.post(
            reverse("dashboard:poll_announce", args=[self.poll.pk]),
            {"winner": stray.pk},
        )
        self.assertEqual(response.status_code, 400)
