"""The email and consent part of the ballot.

Replaces the post-vote email ask: the address is required with the vote,
and the voter says what we may do with it.
"""

import html as html_lib

from django.test import TestCase
from django.urls import reverse

from audience.models import Subscriber, SubscriberStatus
from cinema.models import EmailPreference, Film, Poll, PollOption, PollStatus, Vote


class VoteContactTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )

    def cast(self, remote_addr="127.0.0.1", **overrides):
        data = {
            "poll": self.poll.pk,
            "option": self.option.pk,
            "email": "Fan@Example.com",
            "email_preference": EmailPreference.RESULTS,
        }
        data.update(overrides)
        return self.client.post(
            reverse("vote_cast"),
            data,
            HTTP_HX_REQUEST="true",
            REMOTE_ADDR=remote_addr,
        )

    # --- the ballot ---

    def test_ballot_asks_for_email_and_the_three_choices(self) -> None:
        html = self.client.get(reverse("vote")).content.decode()
        # Required in the browser too, not only on the server.
        self.assertRegex(html, r'<input[^>]*type="email"[^>]*name="email"[^>]*required')
        for value in EmailPreference.values:
            self.assertRegex(
                html,
                rf'<input[^>]*name="email_preference"[^>]*value="{value}"[^>]*required',
            )
        text = html_lib.unescape(html)
        self.assertIn("don't add me to the mailing list", text)
        self.assertIn("Add me to the mailing list", text)
        self.assertIn("Don't email me", text)

    def test_copy_does_not_promise_a_newsletter(self) -> None:
        for page in (self.client.get(reverse("vote")), self.cast()):
            html = page.content.decode().lower()
            self.assertNotIn("newsletter", html)
            self.assertNotIn("weekly", html)

    # --- what gets stored ---

    def test_vote_keeps_the_address_and_the_choice(self) -> None:
        self.cast()
        vote = Vote.objects.get()
        self.assertEqual(vote.email, "fan@example.com")
        self.assertEqual(vote.email_preference, EmailPreference.RESULTS)

    def test_results_only_does_not_join_the_mailing_list(self) -> None:
        response = self.cast(email_preference=EmailPreference.RESULTS)
        self.assertEqual(Subscriber.objects.count(), 0)
        self.assertIn("once with what won", response.content.decode())

    def test_do_not_email_me_stores_the_address_but_nothing_else(self) -> None:
        response = self.cast(email_preference=EmailPreference.NONE)
        self.assertEqual(Subscriber.objects.count(), 0)
        self.assertFalse(Vote.objects.get().wants_email)
        self.assertNotIn("we'll email", response.content.decode())

    def test_mailing_list_choice_creates_a_subscriber(self) -> None:
        response = self.cast(
            email_preference=EmailPreference.SUBSCRIBE, remote_addr="198.51.100.4"
        )
        sub = Subscriber.objects.get()
        self.assertEqual(sub.email, "fan@example.com")
        self.assertEqual(sub.source, "poll_vote")
        self.assertEqual(sub.status, SubscriberStatus.ACTIVE)
        self.assertEqual(sub.consent_ip, "198.51.100.4")
        self.assertIn("You're on the list", response.content.decode())

    def test_unsubscribed_address_is_not_resurrected(self) -> None:
        sub, _ = Subscriber.objects.record("gone@example.com", source="poll_vote")
        sub.unsubscribe()
        self.cast(email="gone@example.com", email_preference=EmailPreference.SUBSCRIBE)
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriberStatus.UNSUBSCRIBED)
        self.assertEqual(Vote.objects.count(), 1)  # the vote itself still counts

    # --- refusals ---

    def test_missing_email_is_refused_and_the_ballot_comes_back_filled(self) -> None:
        response = self.cast(email="")
        self.assertEqual(Vote.objects.count(), 0)
        html = response.content.decode()
        self.assertIn("valid email address", html)
        self.assertIn(f'value="{self.option.pk}"\n          checked', html)
        self.assertIn(
            f'id="email-preference-results"\n            value="RESULTS"\n            checked',
            html,
        )

    def test_invalid_email_is_refused(self) -> None:
        self.cast(email="not-an-address")
        self.assertEqual(Vote.objects.count(), 0)

    def test_over_long_email_is_refused(self) -> None:
        email = "a" * 250 + "@example.com"  # passes validate_email, too long to store
        response = self.cast(email=email)
        self.assertEqual(Vote.objects.count(), 0)
        self.assertIn("valid email address", response.content.decode())

    def test_missing_preference_is_refused(self) -> None:
        response = self.cast(email_preference="")
        self.assertEqual(Vote.objects.count(), 0)
        self.assertIn("whether we may email you", response.content.decode())

    def test_unknown_preference_is_refused(self) -> None:
        self.cast(email_preference="PHONE_ME")
        self.assertEqual(Vote.objects.count(), 0)

    def test_same_address_cannot_vote_twice_in_a_round(self) -> None:
        self.cast()
        response = self.cast(email="FAN@example.com")
        self.assertEqual(Vote.objects.count(), 1)
        html = response.content.decode()
        self.assertIn("you only get one vote per round", html)
        self.assertIn('role="status"', html)
        # The ballot comes back filled, in case they meant another address.
        self.assertIn('value="FAN@example.com"', html)

    def test_honeypot_discards_the_vote_without_telling(self) -> None:
        response = self.cast(website="http://spam.example")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vote.objects.count(), 0)
        self.assertEqual(Subscriber.objects.count(), 0)

    def test_plain_post_without_email_shows_the_page_and_stores_nothing(self) -> None:
        response = self.client.post(
            reverse("vote_cast"),
            {"poll": self.poll.pk, "option": self.option.pk, "email": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "web/vote.html")
        self.assertIn("valid email address", response.content.decode())
        self.assertEqual(Vote.objects.count(), 0)
