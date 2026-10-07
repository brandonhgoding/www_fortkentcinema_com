"""The email part of the ballot.

The address is required and is the voter's identity: one vote per
address per round. It is not a mailing-list signup.
"""

import html as html_lib

from django.test import TestCase
from django.urls import reverse

from audience.models import Subscriber, SubscriberStatus
from django.core import signing
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
        html = self.client.get(self.poll.get_absolute_url()).content.decode()
        # Required in the browser too, not only on the server.
        self.assertRegex(html, r'<input[^>]*type="email"[^>]*name="email"[^>]*required')
        self.assertNotIn("email_preference", html)
        self.assertNotIn("mailing list", html_lib.unescape(html).lower())
        self.assertIn("One vote per email address per round", html)

    def test_copy_does_not_promise_a_newsletter(self) -> None:
        for page in (self.client.get(self.poll.get_absolute_url()), self.cast()):
            html = page.content.decode().lower()
            self.assertNotIn("newsletter", html)
            self.assertNotIn("weekly", html)

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


class ThanksScreenSubscribeTests(TestCase):
    """The mailing-list ask after a vote: a separate, explicit yes."""

    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )

    def vote(self, email="fan@example.com"):
        return self.client.post(
            reverse("vote_cast"),
            {"poll": self.poll.pk, "option": self.option.pk, "email": email},
            HTTP_HX_REQUEST="true",
        )

    def _token(self, html: str) -> str:
        import re

        match = re.search(r'name="token" value="([^"]+)"', html)
        assert match, "no subscribe token on the page"
        return match.group(1)

    def test_ask_is_offered_to_an_address_not_on_the_list(self) -> None:
        html = self.vote().content.decode()
        self.assertIn(
            "add\n      <strong>fan@example.com</strong> to our mailing list", html
        )
        self.assertIn(reverse("vote_subscribe"), html)
        self.assertIn("Yes, add me", html)

    def test_ask_is_not_offered_to_a_current_subscriber(self) -> None:
        Subscriber.objects.record("fan@example.com", source="elsewhere")
        html = self.vote().content.decode()
        self.assertNotIn("Yes, add me", html)
        self.assertNotIn("mailing list", html)

    def test_ask_is_not_offered_to_someone_who_opted_out(self) -> None:
        sub, _ = Subscriber.objects.record("fan@example.com", source="elsewhere")
        sub.unsubscribe()
        html = self.vote().content.decode()
        self.assertNotIn("Yes, add me", html)

    def test_saying_yes_joins_the_list_with_the_voting_address(self) -> None:
        token = self._token(self.vote("Fan@Example.com").content.decode())
        response = self.client.post(
            reverse("vote_subscribe"),
            {"token": token},
            HTTP_HX_REQUEST="true",
            REMOTE_ADDR="198.51.100.4",
        )
        self.assertEqual(response.status_code, 200)
        sub = Subscriber.objects.get()
        self.assertEqual(sub.email, "fan@example.com")
        self.assertEqual(sub.source, "poll_vote")
        self.assertEqual(sub.status, SubscriberStatus.ACTIVE)
        self.assertEqual(sub.consent_ip, "198.51.100.4")
        html = response.content.decode()
        self.assertIn("You're on the list", html)
        self.assertNotIn("Yes, add me", html)
        # Still the thanks screen, not a blank ballot.
        self.assertIn("your vote for", html)

    def test_saying_yes_twice_is_not_an_error(self) -> None:
        token = self._token(self.vote().content.decode())
        for _ in range(2):
            response = self.client.post(
                reverse("vote_subscribe"), {"token": token}, HTTP_HX_REQUEST="true"
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(Subscriber.objects.count(), 1)

    def test_a_forged_or_missing_token_is_refused(self) -> None:
        self.vote()
        for token in ("", "junk", signing.dumps(Vote.objects.get().pk, salt="other")):
            response = self.client.post(
                reverse("vote_subscribe"), {"token": token}, HTTP_HX_REQUEST="true"
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Subscriber.objects.count(), 0)

    def test_plain_post_renders_the_whole_page(self) -> None:
        token = self._token(self.vote().content.decode())
        response = self.client.post(reverse("vote_subscribe"), {"token": token})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "web/vote.html")
        self.assertIn("You're on the list", response.content.decode())

    def test_copy_does_not_promise_a_newsletter(self) -> None:
        html = self.vote().content.decode().lower()
        self.assertNotIn("newsletter", html)
        self.assertNotIn("weekly", html)


class ThanksScreenOtherRoundsTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )

    def vote(self):
        return self.client.post(
            reverse("vote_cast"),
            {
                "poll": self.poll.pk,
                "option": self.option.pk,
                "email": "fan@example.com",
            },
            HTTP_HX_REQUEST="true",
        ).content.decode()

    def test_the_next_open_round_is_offered_after_voting(self) -> None:
        other = Poll.objects.create(title="Next classic movie", status=PollStatus.OPEN)
        PollOption.objects.create(poll=other, film=Film.objects.create(title="Alien"))
        html = self.vote()
        # One other round: its ballot is right there, already knowing the
        # address (see test_vote_carry for the token itself).
        self.assertIn("Next up: Next classic movie", html)
        self.assertIn("Alien", html)
        self.assertIn(other.get_absolute_url(), html)
        # Not the round just voted in.
        self.assertNotIn(self.poll.get_absolute_url(), html)

    def test_rounds_beyond_the_next_are_cards(self) -> None:
        for title in ("Next classic movie", "Opening weekend"):
            poll = Poll.objects.create(title=title, status=PollStatus.OPEN)
            PollOption.objects.create(
                poll=poll, film=Film.objects.create(title=f"Film for {title}")
            )
        html = self.vote()
        self.assertIn("Next up: Next classic movie", html)
        self.assertIn("Also open right now", html)
        self.assertIn("Opening weekend", html)

    def test_no_section_when_nothing_else_is_open(self) -> None:
        Poll.objects.create(title="Done", status=PollStatus.CLOSED)
        html = self.vote()
        self.assertNotIn("Next up", html)
        self.assertNotIn("Also open right now", html)
