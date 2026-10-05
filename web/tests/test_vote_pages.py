import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cinema.models import Film, Poll, PollOption, PollStatus, Vote


def _ballot(option, email="fan@example.com"):
    """A complete ballot submission; the email is required."""
    return {"poll": option.poll_id, "option": option.pk, "email": email}


class VotePageTests(TestCase):
    def _open_poll(self) -> Poll:
        poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        PollOption.objects.create(
            poll=poll, film=Film.objects.create(title="Casablanca"), sort_order=1
        )
        PollOption.objects.create(
            poll=poll, film=Film.objects.create(title="The Thing"), sort_order=2
        )
        return poll

    def test_page_renders_with_no_poll(self) -> None:
        response = self.client.get(reverse("vote"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "web/vote.html")

    def test_ballot_lists_every_option(self) -> None:
        self._open_poll()
        html = self.client.get(reverse("vote")).content.decode()
        self.assertIn("Casablanca", html)
        self.assertIn("The Thing", html)

    def test_visiting_sets_no_cookie(self) -> None:
        # The address is the voter's identity; nothing is stored on the browser.
        response = self.client.get(reverse("vote"))
        self.assertEqual(dict(response.cookies), {})

    def test_no_template_comment_leaks(self) -> None:
        self._open_poll()
        html = self.client.get(reverse("vote")).content.decode()
        self.assertNotIn("{#", html)
        self.assertNotIn("{% comment %}", html)


class CastVoteViewTests(TestCase):
    def setUp(self) -> None:
        self.poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.option = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="Casablanca")
        )
        self.other = PollOption.objects.create(
            poll=self.poll, film=Film.objects.create(title="The Thing")
        )

    def test_htmx_post_records_the_vote_and_returns_the_panel(self) -> None:
        response = self.client.post(
            reverse("vote_cast"),
            _ballot(self.option),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "partials/vote_panel.html")
        self.assertEqual(Vote.objects.count(), 1)

    def test_plain_post_renders_the_voted_page(self) -> None:
        # No cookie means a redirect could not show "your vote is in", so the
        # whole page comes back with the voted panel.
        response = self.client.post(reverse("vote_cast"), _ballot(self.option))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "web/vote.html")
        self.assertIn("your vote for", response.content.decode())
        self.assertEqual(Vote.objects.count(), 1)

    def test_voting_twice_from_one_address_keeps_the_first(self) -> None:
        self.client.post(reverse("vote_cast"), _ballot(self.option))
        response = self.client.post(
            reverse("vote_cast"), _ballot(self.other), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vote.objects.count(), 1)
        self.assertEqual(Vote.objects.first().option, self.option)

    def test_returning_to_the_page_shows_the_ballot_again(self) -> None:
        self.client.post(reverse("vote_cast"), _ballot(self.option))
        html = self.client.get(reverse("vote")).content.decode()
        self.assertIn("Cast my vote", html)

    def test_closed_poll_refuses_the_vote(self) -> None:
        self.poll.status = PollStatus.CLOSED
        self.poll.save()
        response = self.client.post(
            reverse("vote_cast"), _ballot(self.option), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vote.objects.count(), 0)

    def test_missing_option_is_a_bad_request_not_a_crash(self) -> None:
        response = self.client.post(
            reverse("vote_cast"), {"poll": self.poll.pk}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_or_unknown_poll_is_a_bad_request(self) -> None:
        for data in ({}, {"poll": "junk"}, {"poll": 999999}):
            response = self.client.post(
                reverse("vote_cast"), data, HTTP_HX_REQUEST="true"
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Vote.objects.count(), 0)

    def test_a_draft_poll_cannot_be_voted_in_by_naming_it(self) -> None:
        draft = Poll.objects.create(title="Secret")
        option = PollOption.objects.create(
            poll=draft, film=Film.objects.create(title="Alien")
        )
        response = self.client.post(
            reverse("vote_cast"), _ballot(option), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Vote.objects.count(), 0)

    def test_two_open_rounds_each_take_their_own_votes(self) -> None:
        second = Poll.objects.create(title="Round Two", status=PollStatus.OPEN)
        option_two = PollOption.objects.create(
            poll=second, film=Film.objects.create(title="Alien")
        )
        self.client.post(reverse("vote_cast"), _ballot(self.option))
        # The same address may vote once in each round.
        self.client.post(reverse("vote_cast"), _ballot(option_two))
        self.assertEqual(Vote.objects.filter(poll=self.poll).count(), 1)
        self.assertEqual(Vote.objects.filter(poll=second).count(), 1)

    def test_voting_sets_no_cookie(self) -> None:
        response = self.client.post(
            reverse("vote_cast"), _ballot(self.option), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(Vote.objects.count(), 1)
        self.assertEqual(dict(response.cookies), {})


class SeveralOpenRoundsTests(TestCase):
    def setUp(self) -> None:
        for title in ("Opening weekend November 11th", "Next classic movie"):
            poll = Poll.objects.create(title=title, status=PollStatus.OPEN)
            PollOption.objects.create(
                poll=poll, film=Film.objects.create(title=f"Film for {title}")
            )

    def test_vote_lists_the_open_rounds_instead_of_a_ballot(self) -> None:
        html = self.client.get(reverse("vote")).content.decode()
        self.assertIn("Pick a round:", html)
        self.assertNotIn("Cast my vote", html)
        for poll in Poll.objects.all():
            self.assertIn(poll.title, html)
            self.assertIn(poll.get_absolute_url(), html)

    def test_each_round_page_shows_only_its_own_ballot(self) -> None:
        first, second = Poll.objects.order_by("pk")
        html = self.client.get(first.get_absolute_url()).content.decode()
        self.assertIn("Cast my vote", html)
        self.assertIn(f'name="poll" value="{first.pk}"', html)
        self.assertIn(first.options.first().film.title, html)
        self.assertNotIn(second.options.first().film.title, html)

    def test_closing_one_round_puts_the_other_ballot_back_on_vote(self) -> None:
        first = Poll.objects.order_by("pk").first()
        first.status = PollStatus.CLOSED
        first.save()
        html = self.client.get(reverse("vote")).content.decode()
        self.assertIn("Cast my vote", html)
        self.assertNotIn("Pick a round:", html)


class VoteArchiveTests(TestCase):
    def test_open_poll_has_its_own_page_with_the_ballot(self) -> None:
        poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        PollOption.objects.create(
            poll=poll, film=Film.objects.create(title="Casablanca")
        )
        response = self.client.get(reverse("vote_archive", kwargs={"slug": poll.slug}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Cast my vote", html)
        self.assertIn(f'name="poll" value="{poll.pk}"', html)

    def test_closed_poll_has_its_own_page(self) -> None:
        poll = Poll.objects.create(title="Round One", status=PollStatus.CLOSED)
        response = self.client.get(reverse("vote_archive", kwargs={"slug": poll.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Round One", response.content.decode())

    def test_lapsed_open_poll_has_its_own_page(self) -> None:
        poll = Poll.objects.create(
            title="Lapsed",
            status=PollStatus.OPEN,
            closes_at=timezone.now() - datetime.timedelta(minutes=1),
        )
        response = self.client.get(reverse("vote_archive", kwargs={"slug": poll.slug}))
        self.assertEqual(response.status_code, 200)

    def test_open_poll_before_its_opens_at_is_not_public(self) -> None:
        poll = Poll.objects.create(
            title="Soon",
            status=PollStatus.OPEN,
            opens_at=timezone.now() + datetime.timedelta(hours=1),
        )
        response = self.client.get(reverse("vote_archive", kwargs={"slug": poll.slug}))
        self.assertEqual(response.status_code, 404)

    def test_draft_poll_is_not_public(self) -> None:
        poll = Poll.objects.create(title="Secret", status=PollStatus.DRAFT)
        response = self.client.get(reverse("vote_archive", kwargs={"slug": poll.slug}))
        self.assertEqual(response.status_code, 404)

    def test_cast_is_not_swallowed_by_the_slug_route(self) -> None:
        # /vote/cast must reach the casting view, not be read as a slug.
        self.assertEqual(reverse("vote_cast"), "/vote/cast")
        response = self.client.get(reverse("vote_cast"))
        self.assertEqual(response.status_code, 405)

    def test_past_rounds_are_linked_from_the_vote_page(self) -> None:
        poll = Poll.objects.create(title="Old Round", status=PollStatus.ANNOUNCED)
        other = Poll.objects.create(title="Older Round", status=PollStatus.CLOSED)
        html = self.client.get(reverse("vote")).content.decode()
        self.assertIn(other.slug, html)
        self.assertIn(poll.title, html)
