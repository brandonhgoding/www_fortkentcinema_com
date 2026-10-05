"""The email part of the ballot.

The address is required and is the voter's identity: one vote per
address per round. It is not a mailing-list signup.
"""

import html as html_lib

from django.test import TestCase
from django.urls import reverse

from audience.models import Subscriber
from cinema.models import Film, Poll, PollOption, PollStatus, Vote


class VoteContactTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )

    def cast(self, **overrides):
        data = {
            "poll": self.poll.pk,
            "option": self.option.pk,
            "email": "Fan@Example.com",
        }
        data.update(overrides)
        return self.client.post(reverse("vote_cast"), data, HTTP_HX_REQUEST="true")

    # --- the ballot ---

    def test_ballot_asks_for_an_email_and_nothing_else(self) -> None:
        html = self.client.get(reverse("vote")).content.decode()
        # Required in the browser too, not only on the server.
        self.assertRegex(html, r'<input[^>]*type="email"[^>]*name="email"[^>]*required')
        self.assertNotIn("email_preference", html)
        self.assertNotIn("mailing list", html_lib.unescape(html).lower())
        self.assertIn("One vote per email address per round", html)

    def test_copy_does_not_promise_a_newsletter(self) -> None:
        for page in (self.client.get(reverse("vote")), self.cast()):
            html = page.content.decode().lower()
            self.assertNotIn("newsletter", html)
            self.assertNotIn("weekly", html)
            self.assertNotIn("we'll email", html)

    # --- what gets stored ---

    def test_vote_keeps_the_address_lowercased(self) -> None:
        self.cast()
        self.assertEqual(Vote.objects.get().email, "fan@example.com")

    def test_voting_never_joins_the_mailing_list(self) -> None:
        self.cast()
        self.assertEqual(Subscriber.objects.count(), 0)

    # --- refusals ---

    def test_missing_email_is_refused_and_the_ballot_comes_back_filled(self) -> None:
        response = self.cast(email="")
        self.assertEqual(Vote.objects.count(), 0)
        html = response.content.decode()
        self.assertIn("valid email address", html)
        self.assertIn(f'value="{self.option.pk}"\n          checked', html)

    def test_invalid_email_is_refused(self) -> None:
        self.cast(email="not-an-address")
        self.assertEqual(Vote.objects.count(), 0)

    def test_over_long_email_is_refused(self) -> None:
        email = "a" * 250 + "@example.com"  # passes validate_email, too long to store
        response = self.cast(email=email)
        self.assertEqual(Vote.objects.count(), 0)
        self.assertIn("valid email address", response.content.decode())

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

    def test_plain_post_without_email_shows_the_page_and_stores_nothing(self) -> None:
        response = self.client.post(
            reverse("vote_cast"),
            {"poll": self.poll.pk, "option": self.option.pk, "email": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "web/vote.html")
        self.assertIn("valid email address", response.content.decode())
        self.assertEqual(Vote.objects.count(), 0)
