from django.test import TestCase
from django.urls import reverse

from cinema.models import Poll, PollStatus


class HomepageHasNoVoteCardTests(TestCase):
    """The home page's vote card came out of Be part of the show on
    2026-10-13; the footer's "You Choose" link is the way in."""

    def test_open_round_adds_no_card(self) -> None:
        Poll.objects.create(title="Round One", status=PollStatus.OPEN)
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("vote-cta", html)
        footer = html[html.index("<footer") :]
        self.assertIn(f'href="{reverse("vote")}"', footer)


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
