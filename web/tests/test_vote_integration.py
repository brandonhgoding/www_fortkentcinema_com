from django.test import TestCase
from django.urls import reverse

from cinema.models import (
    Engagement,
    EngagementFilm,
    Film,
    Poll,
    PollOption,
    PollStatus,
    Screen,
)


class HomepageVoteCTATests(TestCase):
    def test_cta_absent_with_no_open_poll(self) -> None:
        Poll.objects.create(title="Closed Round", status=PollStatus.CLOSED)
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("vote-cta", html)

    def test_cta_present_and_links_to_the_round(self) -> None:
        poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("vote-cta", html)
        self.assertIn(f'href="{poll.get_absolute_url()}"', html)
        self.assertIn("Round One", html)

    def test_one_cta_per_open_round(self) -> None:
        Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        Poll.objects.create(title="Round Two", status=PollStatus.OPEN)
        html = self.client.get(reverse("home")).content.decode()
        self.assertEqual(html.count('class="vote-cta"'), 2)
        self.assertIn("Round One", html)
        self.assertIn("Round Two", html)

    def test_cta_retires_itself_when_the_poll_closes(self) -> None:
        poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.assertIn("vote-cta", self.client.get(reverse("home")).content.decode())
        poll.status = PollStatus.CLOSED
        poll.save()
        self.assertNotIn("vote-cta", self.client.get(reverse("home")).content.decode())


class MoviePageBallotLinkTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(
            name="Screen 1", capacity=100, screen_type="standard",
            aspect_ratio="flat", sound_system="standard", supports_3d=False,
        )
        self.film = Film.objects.create(title="Casablanca")
        engagement = Engagement.objects.create(
            screen=self.screen, start_date="2026-09-01", end_date="2026-09-07"
        )
        # `films` goes through EngagementFilm, which requires an explicit
        # position — .add() cannot supply one.
        EngagementFilm.objects.create(
            engagement=engagement, film=self.film, position=0
        )

    def test_no_link_when_film_is_not_on_a_ballot(self) -> None:
        html = self.client.get(self.film.get_absolute_url()).content.decode()
        self.assertNotIn("movie-ballot-link", html)

    def test_link_shown_when_film_is_on_the_open_ballot(self) -> None:
        poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        PollOption.objects.create(poll=poll, film=self.film)

        html = self.client.get(self.film.get_absolute_url()).content.decode()

        self.assertIn("movie-ballot-link", html)
        self.assertIn(f'href="{poll.get_absolute_url()}"', html)

    def test_no_link_for_a_closed_ballot(self) -> None:
        poll = Poll.objects.create(title="Round One", status=PollStatus.CLOSED)
        PollOption.objects.create(poll=poll, film=self.film)

        html = self.client.get(self.film.get_absolute_url()).content.decode()

        self.assertNotIn("movie-ballot-link", html)


class VoteSitemapTests(TestCase):
    def test_vote_is_listed(self) -> None:
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("/vote", xml)

    def test_archived_polls_are_listed(self) -> None:
        poll = Poll.objects.create(title="Old Round", status=PollStatus.ANNOUNCED)
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertIn(f"/vote/{poll.slug}", xml)

    def test_open_and_draft_polls_are_not_listed(self) -> None:
        draft = Poll.objects.create(title="Draft Round", status=PollStatus.DRAFT)
        live = Poll.objects.create(title="Live Round", status=PollStatus.OPEN)
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn(f"/vote/{draft.slug}", xml)
        self.assertNotIn(f"/vote/{live.slug}", xml)


class VoteCSSBundledTests(TestCase):
    def test_stylesheets_are_registered_in_the_bundle_entry(self) -> None:
        with open("frontend/styles/main.css") as fh:
            main_css = fh.read()
        self.assertIn("VoteCTA.css", main_css)
        self.assertIn("VotePage.css", main_css)

    def test_no_per_page_stylesheet_link_was_added(self) -> None:
        html = self.client.get(reverse("vote")).content.decode()
        self.assertNotIn("VotePage.css", html)
        self.assertIn("css/bundle.css", html)
