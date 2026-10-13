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


def get_involved(html):
    """The Be part of the show section, which holds the vote, open-mic and gift cards."""
    start = html.index('id="get-involved"')
    return html[start : html.index("</section>", start)]


def vote_card(html):
    section = get_involved(html)
    start = section.index("vote-cta")
    return section[start:].split("</article>", 1)[0]


class HomepageVoteCTATests(TestCase):
    def test_cta_absent_with_no_open_poll(self) -> None:
        Poll.objects.create(title="Closed Round", status=PollStatus.CLOSED)
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("vote-cta", html)

    def test_cta_is_generic_and_links_to_the_vote_page(self) -> None:
        Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        html = self.client.get(reverse("home")).content.decode()
        card = vote_card(html)
        self.assertIn("Voting open", card)
        self.assertIn("You choose the film", card)
        self.assertIn("One round is open right now.", card)
        self.assertIn("Cast your vote &rarr;", card)
        self.assertIn(f'href="{reverse("vote")}"', card)
        self.assertIn('data-track="vote_cta_click"', card)
        self.assertNotIn("btn-ticket", card)
        # It does not advertise one round over another.
        self.assertNotIn("Round One", card)

    def test_cta_sits_in_get_involved_above_our_story(self) -> None:
        Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        html = self.client.get(reverse("home")).content.decode()
        self.assertLess(html.index('id="coming-soon"'), html.index('id="get-involved"'))
        self.assertLess(html.index('id="get-involved"'), html.index('id="from-the-booth"'))
        self.assertIn("vote-cta", get_involved(html))

    def test_one_cta_however_many_rounds_are_open(self) -> None:
        for title in ("Round One", "Round Two", "Round Three"):
            Poll.objects.create(title=title, status=PollStatus.OPEN)
        html = self.client.get(reverse("home")).content.decode()
        self.assertEqual(html.count("vote-cta"), 1)
        self.assertIn("3 rounds are open right now.", html)

    def test_cta_retires_itself_when_the_poll_closes(self) -> None:
        poll = Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        self.assertIn("vote-cta", self.client.get(reverse("home")).content.decode())
        poll.status = PollStatus.CLOSED
        poll.save()
        self.assertNotIn("vote-cta", self.client.get(reverse("home")).content.decode())


class MoviePageBallotLinkTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(
            name="Screen 1",
            capacity=100,
            screen_type="standard",
            aspect_ratio="flat",
            sound_system="standard",
            supports_3d=False,
        )
        self.film = Film.objects.create(title="Casablanca")
        engagement = Engagement.objects.create(
            screen=self.screen, start_date="2026-09-01", end_date="2026-09-07"
        )
        # `films` goes through EngagementFilm, which requires an explicit
        # position — .add() cannot supply one.
        EngagementFilm.objects.create(engagement=engagement, film=self.film, position=0)

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
        self.assertIn("HomeSections.css", main_css)
        self.assertIn("VotePage.css", main_css)

    def test_no_per_page_stylesheet_link_was_added(self) -> None:
        html = self.client.get(reverse("vote")).content.decode()
        self.assertNotIn("VotePage.css", html)
        self.assertIn("css/bundle.css", html)
