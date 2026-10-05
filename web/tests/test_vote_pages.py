import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cinema import voting
from cinema.models import Film, Poll, PollOption, PollStatus, Vote


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

    def test_visiting_sets_the_voter_cookie(self) -> None:
        response = self.client.get(reverse("vote"))
        self.assertIn(voting.VOTER_COOKIE, response.cookies)

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
        self.client.cookies[voting.VOTER_COOKIE] = "k1"
        response = self.client.post(
            reverse("vote_cast"),
            {"option": self.option.pk},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "partials/vote_panel.html")
        self.assertEqual(Vote.objects.count(), 1)

    def test_plain_post_redirects_back_to_vote(self) -> None:
        self.client.cookies[voting.VOTER_COOKIE] = "k1"
        response = self.client.post(reverse("vote_cast"), {"option": self.option.pk})
        self.assertRedirects(response, reverse("vote"))
        self.assertEqual(Vote.objects.count(), 1)

    def test_voting_twice_shows_the_voted_state_not_a_500(self) -> None:
        self.client.cookies[voting.VOTER_COOKIE] = "k1"
        self.client.post(reverse("vote_cast"), {"option": self.option.pk})
        response = self.client.post(
            reverse("vote_cast"), {"option": self.other.pk}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vote.objects.count(), 1)
        self.assertEqual(Vote.objects.first().option, self.option)

    def test_closed_poll_refuses_the_vote(self) -> None:
        self.poll.status = PollStatus.CLOSED
        self.poll.save()
        self.client.cookies[voting.VOTER_COOKIE] = "k1"
        response = self.client.post(
            reverse("vote_cast"), {"option": self.option.pk}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vote.objects.count(), 0)

    def test_missing_option_is_a_bad_request_not_a_crash(self) -> None:
        self.client.cookies[voting.VOTER_COOKIE] = "k1"
        response = self.client.post(reverse("vote_cast"), {}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 400)

    def test_vote_without_a_cookie_still_works_and_sets_one(self) -> None:
        response = self.client.post(
            reverse("vote_cast"), {"option": self.option.pk}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(Vote.objects.count(), 1)
        self.assertIn(voting.VOTER_COOKIE, response.cookies)


class VoteArchiveTests(TestCase):
    def test_open_poll_slug_redirects_to_the_canonical_page(self) -> None:
        poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        response = self.client.get(
            reverse("vote_archive", kwargs={"slug": poll.slug})
        )
        self.assertRedirects(response, reverse("vote"))

    def test_closed_poll_has_its_own_page(self) -> None:
        poll = Poll.objects.create(title="Round One", status=PollStatus.CLOSED)
        response = self.client.get(
            reverse("vote_archive", kwargs={"slug": poll.slug})
        )
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
        response = self.client.get(
            reverse("vote_archive", kwargs={"slug": poll.slug})
        )
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
