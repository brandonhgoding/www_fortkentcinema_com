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
        poll = self._open_poll()
        html = self.client.get(poll.get_absolute_url()).content.decode()
        self.assertIn("Casablanca", html)
        self.assertIn("The Thing", html)
        self.assertIn("Cast my vote", html)

    def test_vote_page_lists_the_open_round_with_its_posters(self) -> None:
        poll = self._open_poll()
        poll.options.filter(film__title="Casablanca").update()
        film = poll.options.get(film__title="Casablanca").film
        film.poster_url = "https://img/casablanca.jpg"
        film.save()
        html = self.client.get(reverse("vote")).content.decode()
        self.assertIn('class="vote-round"', html)
        self.assertIn(f'href="{poll.get_absolute_url()}"', html)
        self.assertIn('src="https://img/casablanca.jpg"', html)
        self.assertIn('<span class="vote-round__poster-blank">The Thing</span>', html)
        self.assertNotIn("Cast my vote", html)
        # A single open round is not asked to be picked from.
        self.assertNotIn("Pick a round", html)
        self.assertIn("One round is open right now.", html)

    def test_visiting_sets_no_cookie(self) -> None:
        # The address is the voter's identity; nothing is stored on the browser.
        response = self.client.get(reverse("vote"))
        # Django's CSRF cookie is the only one allowed; no voter token.
        self.assertEqual(set(response.cookies) - {"csrftoken"}, set())

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

    def test_returning_to_the_round_shows_the_ballot_again(self) -> None:
        self.client.post(reverse("vote_cast"), _ballot(self.option))
        html = self.client.get(self.poll.get_absolute_url()).content.decode()
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

    def test_a_scheduled_poll_cannot_be_voted_in_or_seen_by_naming_it(self) -> None:
        """OPEN but before opens_at is not public yet; /vote/<slug> 404s it.
        Naming it on /vote/cast must give the same nothing: not a vote, and
        not the shortlist either (the page used to render the ballot's
        posters even as it refused the vote, and option pks are guessable)."""
        soon = Poll.objects.create(
            title="Soon",
            status=PollStatus.OPEN,
            opens_at=timezone.now() + datetime.timedelta(hours=1),
        )
        option = PollOption.objects.create(
            poll=soon,
            film=Film.objects.create(
                title="Secret Film", poster_url="https://img.example/secret.jpg"
            ),
        )
        for data in (_ballot(option), {"poll": soon.pk, "option": 999999,
                                       "email": "fan@example.com"}):
            response = self.client.post(
                reverse("vote_cast"), data, HTTP_HX_REQUEST="true"
            )
            self.assertEqual(response.status_code, 400)
            html = response.content.decode()
            self.assertNotIn("Secret Film", html)
            self.assertNotIn("secret.jpg", html)
        self.assertEqual(Vote.objects.count(), 0)

    def test_junk_option_id_is_a_bad_request_not_a_crash(self) -> None:
        for option in ("abc", "1.5", "9" * 30):
            response = self.client.post(
                reverse("vote_cast"),
                {"poll": self.poll.pk, "option": option, "email": "fan@example.com"},
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(response.status_code, 400, option)
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
        # Django's CSRF cookie is the only one allowed; no voter token.
        self.assertEqual(set(response.cookies) - {"csrftoken"}, set())


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

    def test_closing_one_round_leaves_a_single_card_on_vote(self) -> None:
        first, second = Poll.objects.order_by("pk")
        first.status = PollStatus.CLOSED
        first.save()
        html = self.client.get(reverse("vote")).content.decode()
        self.assertEqual(html.count('class="vote-round"'), 1)
        self.assertIn(second.title, html)
        self.assertNotIn("Pick a round:", html)

    def test_every_open_round_is_listed_however_many(self) -> None:
        for i in range(5):
            poll = Poll.objects.create(title=f"Extra {i}", status=PollStatus.OPEN)
            PollOption.objects.create(
                poll=poll, film=Film.objects.create(title=f"Extra film {i}")
            )
        html = self.client.get(reverse("vote")).content.decode()
        self.assertEqual(html.count('class="vote-round"'), 7)


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


class VoteHeroTests(TestCase):
    def test_hero_fans_the_ballot_posters_with_a_blank_for_missing_art(self) -> None:
        poll = Poll.objects.create(
            title="Opening weekend",
            status=PollStatus.OPEN,
            closes_at=timezone.now() + datetime.timedelta(days=3),
        )
        PollOption.objects.create(
            poll=poll,
            film=Film.objects.create(title="Dune", poster_url="https://img/dune.jpg"),
            sort_order=1,
        )
        PollOption.objects.create(
            poll=poll, film=Film.objects.create(title="Wicked"), sort_order=2
        )
        html = self.client.get(poll.get_absolute_url()).content.decode()
        self.assertIn('class="vote-hero"', html)
        self.assertIn('src="https://img/dune.jpg"', html)
        self.assertIn('<span class="vote-hero__poster-blank">Wicked</span>', html)
        self.assertIn("2 films on the ballot.", html)
        self.assertIn("Voting closes", html)
        self.assertIn('href="#vote-panel"', html)
        self.assertIn("Cast your vote", html)

    def test_vote_page_hero_with_one_round_sends_you_straight_to_it(self) -> None:
        poll = Poll.objects.create(title="Only round", status=PollStatus.OPEN)
        PollOption.objects.create(poll=poll, film=Film.objects.create(title="Dune"))
        html = self.client.get(reverse("vote")).content.decode()
        self.assertIn(
            f'href="{poll.get_absolute_url()}" class="btn btn-primary vote-hero__cta"',
            html,
        )
        self.assertIn("Cast your vote", html)

    def test_hero_shows_at_most_six_posters(self) -> None:
        poll = Poll.objects.create(title="Big round", status=PollStatus.OPEN)
        for i in range(8):
            PollOption.objects.create(
                poll=poll, film=Film.objects.create(title=f"Film {i}"), sort_order=i
            )
        html = self.client.get(poll.get_absolute_url()).content.decode()
        self.assertEqual(html.count('class="vote-hero__poster"'), 6)
        self.assertIn("8 films on the ballot.", html)
        # The round's card on /vote shows every poster, uncapped.
        html = self.client.get(reverse("vote")).content.decode()
        self.assertEqual(html.count('class="vote-round__poster"'), 8)

    def test_chooser_hero_takes_a_film_from_each_open_round(self) -> None:
        for title, films in (("Round A", ["A1", "A2"]), ("Round B", ["B1"])):
            poll = Poll.objects.create(title=title, status=PollStatus.OPEN)
            for i, name in enumerate(films):
                PollOption.objects.create(
                    poll=poll, film=Film.objects.create(title=name), sort_order=i
                )
        html = self.client.get(reverse("vote")).content.decode()
        posters = html.split('class="vote-hero__poster"')[1:]
        self.assertEqual(len(posters), 3)
        # Oldest round first, alternating between rounds before going
        # deeper into one ballot.
        self.assertIn("A1", posters[0])
        self.assertIn("B1", posters[1])
        self.assertIn("A2", posters[2])
        self.assertIn("2 rounds are open", html)
        self.assertIn("Pick a round", html)

    def test_decided_round_hero_has_no_call_to_action(self) -> None:
        poll = Poll.objects.create(title="Done", status=PollStatus.CLOSED)
        PollOption.objects.create(
            poll=poll, film=Film.objects.create(title="Casablanca")
        )
        html = self.client.get(reverse("vote")).content.decode()
        self.assertIn("Voting has closed.", html)
        self.assertNotIn("Cast your vote", html)
        self.assertNotIn('href="#vote-panel"', html)

    def test_no_poll_hero_still_renders(self) -> None:
        html = self.client.get(reverse("vote")).content.decode()
        self.assertIn("You pick the picture", html)
        self.assertNotIn("vote-hero__posters", html)


class VoteWordingTests(TestCase):
    """The audit: round cards named their films only in hover tooltips, and
    the page described itself as a classic night while the rounds were new
    releases."""

    def test_round_card_names_its_films_in_text(self) -> None:
        poll = Poll.objects.create(title="Opening weekend", status=PollStatus.OPEN)
        for i, title in enumerate(("Dune", "Wicked", "Sinners")):
            PollOption.objects.create(
                poll=poll, film=Film.objects.create(title=title), sort_order=i
            )
        Poll.objects.create(title="Another round", status=PollStatus.OPEN)
        html = self.client.get(reverse("vote")).content.decode()
        meta = html.split('class="vote-round__meta">', 1)[1].split("</span>", 1)[0]
        self.assertIn("On the ballot: Dune, Wicked and Sinners.", " ".join(meta.split()))

    def test_page_no_longer_calls_itself_a_classic_night(self) -> None:
        html = self.client.get(reverse("vote")).content.decode().lower()
        self.assertEqual(html.count("classic"), 0)
