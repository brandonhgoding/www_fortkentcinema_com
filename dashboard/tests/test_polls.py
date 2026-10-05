import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cinema.models import EmailPreference, Film, Poll, PollOption, PollStatus, Vote

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
        self.assertEqual(self.client.get(reverse("dashboard:polls")).status_code, 302)
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(self.client.get(reverse("dashboard:polls")).status_code, 403)

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


class PollDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.film = Film.objects.create(title="Casablanca")
        option = PollOption.objects.create(poll=self.poll, film=self.film)
        Vote.objects.create(poll=self.poll, option=option, voter_key="k1")
        Vote.objects.create(poll=self.poll, option=option, voter_key="k2")

    def test_delete_takes_the_ballot_and_votes_with_it(self) -> None:
        self.client.post(reverse("dashboard:poll_delete", args=[self.poll.pk]))
        self.assertFalse(Poll.objects.filter(pk=self.poll.pk).exists())
        self.assertEqual(PollOption.objects.count(), 0)
        self.assertEqual(Vote.objects.count(), 0)
        # The film is only referenced by the ballot; it stays.
        self.assertTrue(Film.objects.filter(pk=self.film.pk).exists())

    def test_delete_leaves_the_engagement_alone(self) -> None:
        from cinema.models import Engagement, Screen
        import datetime

        screen = Screen.objects.create(
            name="Main",
            capacity=100,
            screen_type="standard",
            aspect_ratio="flat",
            sound_system="standard",
            supports_3d=False,
        )
        engagement = Engagement.objects.create(
            screen=screen,
            start_date=datetime.date(2026, 11, 1),
            end_date=datetime.date(2026, 11, 7),
        )
        self.poll.status = PollStatus.ANNOUNCED
        self.poll.winner = self.poll.options.first()
        self.poll.engagement = engagement
        self.poll.save()

        self.client.post(reverse("dashboard:poll_delete", args=[self.poll.pk]))
        self.assertTrue(Engagement.objects.filter(pk=engagement.pk).exists())

    def test_htmx_delete_from_the_list_swaps_the_list_and_toasts(self) -> None:
        response = self.client.post(
            reverse("dashboard:poll_delete", args=[self.poll.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="poll-list" hx-swap-oob="true"', html)
        self.assertNotIn("Round One", html)
        trigger = json.loads(response["HX-Trigger"])
        self.assertEqual(trigger["dashboard-toast"]["message"], "Deleted Round One")

    def test_form_delete_from_the_detail_page_redirects_to_the_list(self) -> None:
        response = self.client.post(
            reverse("dashboard:poll_delete", args=[self.poll.pk]), follow=True
        )
        self.assertRedirects(response, reverse("dashboard:polls"))
        self.assertIn("Deleted Round One", response.content.decode())

    def test_delete_is_post_only(self) -> None:
        response = self.client.get(
            reverse("dashboard:poll_delete", args=[self.poll.pk])
        )
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Poll.objects.filter(pk=self.poll.pk).exists())

    def test_requires_staff(self) -> None:
        self.client.logout()
        response = self.client.post(
            reverse("dashboard:poll_delete", args=[self.poll.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Poll.objects.filter(pk=self.poll.pk).exists())

    def test_both_pages_offer_delete_with_a_confirm_naming_the_votes(self) -> None:
        url = reverse("dashboard:poll_delete", args=[self.poll.pk])
        list_html = self.client.get(reverse("dashboard:polls")).content.decode()
        self.assertIn(f'hx-post="{url}"', list_html)
        self.assertIn("2 votes go with it", list_html)
        detail_html = self.client.get(
            reverse("dashboard:poll_detail", args=[self.poll.pk])
        ).content.decode()
        self.assertIn(f'action="{url}"', detail_html)
        self.assertIn("2 votes go with it", detail_html)


class PollVotersTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )
        Vote.objects.create(
            poll=self.poll,
            option=option,
            voter_key="k1",
            email="=results@example.com",
            email_preference=EmailPreference.RESULTS,
        )
        Vote.objects.create(
            poll=self.poll,
            option=option,
            voter_key="k2",
            email="list@example.com",
            email_preference=EmailPreference.SUBSCRIBE,
        )
        Vote.objects.create(
            poll=self.poll,
            option=option,
            voter_key="k3",
            email="quiet@example.com",
            email_preference=EmailPreference.NONE,
        )
        Vote.objects.create(poll=self.poll, option=option, voter_key="k4")  # legacy

    def test_detail_counts_each_choice_and_offers_the_export(self) -> None:
        html = self.client.get(
            reverse("dashboard:poll_detail", args=[self.poll.pk])
        ).content.decode()
        self.assertIn("Voters", html)
        self.assertIn("Download 2 emails (CSV)", html)
        self.assertIn(reverse("dashboard:poll_votes_export", args=[self.poll.pk]), html)

    def test_detail_hides_the_export_when_nobody_may_be_emailed(self) -> None:
        self.poll.votes.exclude(email_preference=EmailPreference.NONE).delete()
        html = self.client.get(
            reverse("dashboard:poll_detail", args=[self.poll.pk])
        ).content.decode()
        self.assertNotIn("Download", html)

    def test_export_lists_only_those_who_may_be_emailed(self) -> None:
        response = self.client.get(
            reverse("dashboard:poll_votes_export", args=[self.poll.pk])
        )
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("poll-round-one-emails.csv", response["Content-Disposition"])
        rows = response.content.decode().splitlines()
        self.assertEqual(rows[0], "email,preference,film,voted_at")
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[1].startswith("'=results@example.com,RESULTS,Casablanca,"))
        self.assertTrue(rows[2].startswith("list@example.com,SUBSCRIBE,Casablanca,"))
        self.assertNotIn("quiet@example.com", response.content.decode())

    def test_export_requires_staff(self) -> None:
        self.client.logout()
        response = self.client.get(
            reverse("dashboard:poll_votes_export", args=[self.poll.pk])
        )
        self.assertEqual(response.status_code, 302)
