import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cinema.models import Poll, PollStatus

User = get_user_model()


class PollListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:polls")).content.decode()
        self.assertIn("empty-state", html)
        self.assertIn("No Polls Yet", html)

    def test_rows_show_title_and_status(self) -> None:
        Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        html = self.client.get(reverse("dashboard:polls")).content.decode()
        self.assertIn("Round One", html)
        self.assertIn("Open", html)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:polls")).status_code, 302
        )
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(
            self.client.get(reverse("dashboard:polls")).status_code, 403
        )

    def test_polls_css_linked(self) -> None:
        html = self.client.get(reverse("dashboard:polls")).content.decode()
        self.assertIn("dashboard/css/polls.css", html)

    def test_sidebar_links_to_polls(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(reverse("dashboard:polls"), html)


class PollCreateEditTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_create_form_renders(self) -> None:
        response = self.client.get(reverse("dashboard:poll_create"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Create Poll", response.content.decode())

    def test_create_saves_a_draft(self) -> None:
        self.client.post(
            reverse("dashboard:poll_create"),
            {"title": "Round One", "blurb": "Pick one", "results_visible": "on"},
        )
        poll = Poll.objects.get()
        self.assertEqual(poll.title, "Round One")
        self.assertEqual(poll.status, PollStatus.DRAFT)
        self.assertTrue(poll.results_visible)

    def test_create_rejects_a_blank_title(self) -> None:
        response = self.client.post(reverse("dashboard:poll_create"), {"title": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Poll.objects.count(), 0)

    def test_invalid_submit_stays_in_the_drawer(self) -> None:
        # The form re-renders into the drawer; it used to replace the list.
        response = self.client.post(reverse("dashboard:poll_create"), {"title": ""})
        html = response.content.decode()
        self.assertIn('hx-target="#drawer-content"', html)
        self.assertNotIn('id="poll-list"', html)
        self.assertNotIn("HX-Trigger", response)

    def test_success_swaps_the_list_and_closes_the_drawer(self) -> None:
        response = self.client.post(
            reverse("dashboard:poll_create"), {"title": "Round One", "blurb": ""}
        )
        self.assertIn('id="poll-list" hx-swap-oob="true"', response.content.decode())
        trigger = json.loads(response["HX-Trigger"])
        self.assertTrue(trigger["close-drawer"])
        self.assertEqual(trigger["dashboard-toast"]["message"], "Poll created")

    def test_edit_updates_the_poll(self) -> None:
        poll = Poll.objects.create(title="Round One")
        self.client.post(
            reverse("dashboard:poll_edit", args=[poll.pk]),
            {"title": "Round One Renamed", "blurb": ""},
        )
        poll.refresh_from_db()
        self.assertEqual(poll.title, "Round One Renamed")

    def test_results_visible_can_be_turned_off(self) -> None:
        poll = Poll.objects.create(title="Round One", results_visible=True)
        self.client.post(
            reverse("dashboard:poll_edit", args=[poll.pk]),
            {"title": "Round One", "blurb": ""},
        )
        poll.refresh_from_db()
        self.assertFalse(poll.results_visible)
