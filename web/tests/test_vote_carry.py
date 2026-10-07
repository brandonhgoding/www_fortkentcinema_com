"""Carrying the address from one round to the next.

A voter with several rounds open should type the address once. The thanks
screen signs the vote just cast and puts that token on the cards for the
other open rounds, so each of their ballots already knows the address.
Nothing is stored on the browser: the token is the only thing that
travels, and it lapses in a day.
"""

import time
from unittest import mock

from django.core import signing
from django.test import TestCase
from django.urls import reverse

from cinema.models import Film, Poll, PollOption, PollStatus, Vote

EMAIL = "fan@example.com"


def _round(title: str, *films: str) -> Poll:
    poll = Poll.objects.create(title=title, status=PollStatus.OPEN)
    for n, film in enumerate(films, start=1):
        PollOption.objects.create(
            poll=poll, film=Film.objects.create(title=film), sort_order=n
        )
    return poll


def _token(vote: Vote) -> str:
    return signing.dumps(vote.pk, salt="vote-voter")


class CarryAddressTests(TestCase):
    def setUp(self) -> None:
        self.first = _round("Round One", "Casablanca", "The Thing")
        self.second = _round("Round Two", "Alien", "Jaws")

    def cast(self, poll, option, **extra):
        data = {"poll": poll.pk, "option": option.pk}
        data.update(extra)
        return self.client.post(reverse("vote_cast"), data, HTTP_HX_REQUEST="true")

    def vote_in_first(self):
        option = self.first.options.first()
        response = self.cast(self.first, option, email=EMAIL)
        return response.content.decode(), Vote.objects.get(poll=self.first)

    # --- the thanks screen ---

    def test_thanks_screen_lists_the_other_rounds_with_the_token(self) -> None:
        third = _round("Round Three", "Heat")
        html, vote = self.vote_in_first()
        token = _token(vote)
        self.assertIn("Also open right now", html)
        # Open rounds run oldest first, the same order as the /vote list.
        self.assertIn(f'href="{self.second.get_absolute_url()}?voter={token}"', html)
        self.assertIn(f'href="{third.get_absolute_url()}?voter={token}"', html)
        # No ballot on the thanks screen: the next vote is a click away.
        self.assertNotIn("Cast my vote", html)
        self.assertNotIn("Voting as", html)

    def test_no_section_when_nothing_else_is_open(self) -> None:
        self.second.status = PollStatus.CLOSED
        self.second.save()
        html, vote = self.vote_in_first()
        self.assertNotIn("Also open right now", html)
        self.assertNotIn("?voter=", html)

    def test_submitting_brings_the_top_of_the_panel_into_view(self) -> None:
        # The ballot can sit well below the hero; after the swap the thanks
        # line is at the top of the new panel, so scroll to it.
        html = self.client.get(self.second.get_absolute_url()).content.decode()
        self.assertIn('hx-swap="outerHTML show:#vote-panel:top"', html)

    def test_thanks_screen_sets_no_cookie(self) -> None:
        option = self.first.options.first()
        response = self.cast(self.first, option, email=EMAIL)
        self.assertEqual(set(response.cookies) - {"csrftoken"}, set())

    # --- casting by token ---

    def test_casting_with_a_token_records_the_vote_under_that_address(self) -> None:
        _, vote = self.vote_in_first()
        option = self.second.options.get(film__title="Jaws")
        response = self.cast(self.second, option, token=_token(vote))
        self.assertEqual(response.status_code, 200)
        second_vote = Vote.objects.get(poll=self.second)
        self.assertEqual(second_vote.email, EMAIL)
        self.assertEqual(second_vote.option, option)
        html = response.content.decode()
        self.assertIn("your vote for", html)
        self.assertIn("Jaws", html)

    def test_token_chain_continues_to_the_round_after(self) -> None:
        third = _round("Round Three", "Heat")
        _, vote = self.vote_in_first()
        option = self.second.options.first()
        response = self.cast(self.second, option, token=_token(vote))
        html = response.content.decode()
        second_vote = Vote.objects.get(poll=self.second)
        # The next card is signed with the vote just cast, not the first one.
        self.assertIn(
            f'href="{third.get_absolute_url()}?voter={_token(second_vote)}"', html
        )

    def test_rounds_this_address_already_voted_in_are_not_offered(self) -> None:
        third = _round("Round Three", "Heat")
        _, vote = self.vote_in_first()
        # Skip ahead to Round Three from a card; Round One is done, so the
        # only thing left to offer is Round Two.
        response = self.cast(third, third.options.first(), token=_token(vote))
        html = response.content.decode()
        self.assertIn(f'href="{self.second.get_absolute_url()}?voter=', html)
        self.assertNotIn(self.first.get_absolute_url(), html)

    def test_nothing_left_once_every_round_has_this_vote(self) -> None:
        _, vote = self.vote_in_first()
        response = self.cast(
            self.second, self.second.options.first(), token=_token(vote)
        )
        html = response.content.decode()
        self.assertNotIn("Also open right now", html)

    def test_token_does_not_bypass_one_vote_per_address(self) -> None:
        _, vote = self.vote_in_first()
        option = self.second.options.first()
        self.cast(self.second, option, email=EMAIL)
        response = self.cast(self.second, option, token=_token(vote))
        html = response.content.decode()
        self.assertEqual(Vote.objects.filter(poll=self.second).count(), 1)
        self.assertIn("already cast one", html)
        # The ballot stays in token mode: nothing to retype.
        self.assertIn(f'name="token" value="{_token(vote)}"', html)

    def test_a_forged_token_falls_back_to_asking_for_the_address(self) -> None:
        self.vote_in_first()
        option = self.second.options.first()
        response = self.cast(self.second, option, token="forged:junk")
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vote.objects.filter(poll=self.second).count(), 0)
        self.assertIn('name="email"', html)
        self.assertNotIn('name="token"', html)
        self.assertIn("enter your email", html)
        # The pick survives the round trip.
        self.assertIn(f'value="{option.pk}"\n          checked', html)

    def test_a_token_for_a_vote_without_an_address_is_ignored(self) -> None:
        legacy = Vote.objects.create(
            poll=self.first, option=self.first.options.first(), email=""
        )
        option = self.second.options.first()
        response = self.cast(self.second, option, token=_token(legacy))
        self.assertEqual(Vote.objects.filter(poll=self.second).count(), 0)
        self.assertIn('name="email"', response.content.decode())

    def test_token_and_email_together_prefer_the_token(self) -> None:
        _, vote = self.vote_in_first()
        option = self.second.options.first()
        self.cast(self.second, option, token=_token(vote), email="other@example.com")
        self.assertEqual(Vote.objects.get(poll=self.second).email, EMAIL)

    # --- the round page ---

    def test_round_page_with_a_token_renders_the_ballot_in_token_mode(self) -> None:
        _, vote = self.vote_in_first()
        url = f"{self.second.get_absolute_url()}?voter={_token(vote)}"
        html = self.client.get(url).content.decode()
        self.assertIn(f'name="token" value="{_token(vote)}"', html)
        self.assertNotIn('name="email"', html)
        self.assertIn(f"Voting as <strong>{EMAIL}</strong>", html)
        # The way out for a second person at the same keyboard.
        self.assertIn(f'href="{self.second.get_absolute_url()}"', html)
        self.assertIn("Use a different address", html)
        # Same place as the email field: above the films.
        self.assertLess(html.index("Voting as"), html.index('name="option"'))

    def test_round_page_with_a_bad_token_renders_the_plain_ballot(self) -> None:
        url = f"{self.second.get_absolute_url()}?voter=not-a-token"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('name="email"', html)
        self.assertNotIn('name="token"', html)

    def test_round_page_without_a_token_is_unchanged(self) -> None:
        html = self.client.get(self.second.get_absolute_url()).content.decode()
        self.assertIn('name="email"', html)
        self.assertNotIn('name="token"', html)
        self.assertNotIn("Voting as", html)

    def test_token_lapses_after_a_day(self) -> None:
        _, vote = self.vote_in_first()
        # A signature stamped two days ago.
        two_days_ago = time.time() - 2 * 86400
        with mock.patch("django.core.signing.time.time", return_value=two_days_ago):
            stale = signing.dumps(vote.pk, salt="vote-voter")
        url = f"{self.second.get_absolute_url()}?voter={stale}"
        html = self.client.get(url).content.decode()
        self.assertIn('name="email"', html)
        self.assertNotIn('name="token"', html)
