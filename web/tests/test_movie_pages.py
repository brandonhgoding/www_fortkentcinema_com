"""Per-movie pages (/movies/<slug>) and Movie/ScreeningEvent structured data.

Two things are load-bearing and easy to regress:

1. Only *booked* films get a page. A film we've never played has no showtimes and
   no run history — nothing but the TMDB blurb every other cinema site publishes.
   Shipping those would be 20 duplicate-content pages.
2. The pages must be reachable by following links. The blog's 77 posts sat
   unindexed for exactly this reason.
"""

import datetime
import json
import re

from blog.models import BlogAuthor, BlogCategory, BlogPost
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.test import TestCase
from django.utils import timezone


def hrefs(html):
    return re.findall(r'<a[^>]+href="([^"]+)"', html)


def jsonld_blocks(html):
    return [
        json.loads(m)
        for m in re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
        )
    ]


def movie_jsonld(html):
    for block in jsonld_blocks(html):
        if block.get("@type") == "Movie":
            return block
    return None


class MoviePageFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.screen = Screen.objects.create(name="Screen 1", capacity=100)

        cls.showing = Film.objects.create(
            title="The Odyssey",
            runtime_minutes=120,
            rating="PG-13",
            synopsis="A long way home.",
            poster_url="https://image.tmdb.org/t/p/w500/odyssey.jpg",
            imdb_id="tt1234567",
            youtube_id="abc123",
        )
        cls.archived = Film.objects.create(
            title="Carnival of Souls",
            runtime_minutes=78,
            overview="A TMDB blurb.",
            poster_url="https://image.tmdb.org/t/p/w500/carnival.jpg",
        )
        cls.never_booked = Film.objects.create(
            title="Never Played Here",
            runtime_minutes=90,
            overview="Nobody booked this.",
        )

        today = timezone.localdate()

        # Currently showing, with a future showtime.
        cls.current_eng = Engagement.objects.create(
            screen=cls.screen,
            start_date=today,
            end_date=today + datetime.timedelta(days=6),
            status="CONFIRMED",
        )
        EngagementFilm.objects.create(
            engagement=cls.current_eng, film=cls.showing, position=0
        )
        cls.future_showtime = Showtime.objects.create(
            engagement=cls.current_eng,
            screen=cls.screen,
            starts_at=timezone.now() + datetime.timedelta(days=1, hours=2),
        )
        # A past showtime on the same engagement — must NOT become a ScreeningEvent.
        cls.past_showtime = Showtime.objects.create(
            engagement=cls.current_eng,
            screen=cls.screen,
            starts_at=timezone.now() - datetime.timedelta(days=1),
        )

        # Played last year, nothing upcoming.
        cls.past_eng = Engagement.objects.create(
            screen=cls.screen,
            start_date=today - datetime.timedelta(days=300),
            end_date=today - datetime.timedelta(days=294),
            status="CONFIRMED",
        )
        EngagementFilm.objects.create(
            engagement=cls.past_eng, film=cls.archived, position=0
        )
        Showtime.objects.create(
            engagement=cls.past_eng,
            screen=cls.screen,
            starts_at=timezone.now() - datetime.timedelta(days=298),
        )


class PageInventoryTests(MoviePageFixture):
    def test_booked_film_has_a_page(self):
        self.assertEqual(self.client.get(f"/movies/{self.showing.slug}").status_code, 200)

    def test_previously_played_film_keeps_its_page(self):
        """A run ending must turn the page into an archive, not a 404."""
        self.assertEqual(self.client.get(f"/movies/{self.archived.slug}").status_code, 200)

    def test_never_booked_film_has_no_page(self):
        """Nothing local to say -> duplicate TMDB text -> no page."""
        self.assertEqual(
            self.client.get(f"/movies/{self.never_booked.slug}").status_code, 404
        )

    def test_never_booked_film_absent_from_sitemap(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertIn(f"/movies/{self.showing.slug}", xml)
        self.assertIn(f"/movies/{self.archived.slug}", xml)
        self.assertNotIn(f"/movies/{self.never_booked.slug}", xml)


class MoviePageContentTests(MoviePageFixture):
    def test_now_showing_page_renders_showtimes(self):
        html = self.client.get(f"/movies/{self.showing.slug}").content.decode()
        self.assertIn("NOW SHOWING", html)
        self.assertIn("SHOWTIMES", html)
        self.assertIn("Screen 1", html)

    def test_archive_page_renders_run_history_not_fake_showtimes(self):
        html = self.client.get(f"/movies/{self.archived.slug}").content.decode()
        self.assertIn("AT FORT KENT CINEMA", html)
        self.assertIn("played at Fort Kent Cinema", html)
        self.assertNotIn("SHOWTIMES", html)

    def test_title_leads_with_the_local_hook(self):
        html = self.client.get(f"/movies/{self.showing.slug}").content.decode()
        self.assertIn("<title>The Odyssey — Showtimes | Fort Kent Cinema</title>", html)

    def test_description_falls_back_to_overview_when_no_synopsis(self):
        html = self.client.get(f"/movies/{self.archived.slug}").content.decode()
        self.assertIn("A TMDB blurb.", html)

    def test_film_without_review_renders_no_review_link(self):
        html = self.client.get(f"/movies/{self.showing.slug}").content.decode()
        self.assertNotIn("Read our review", html)


class ReviewLinkTests(MoviePageFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        cat = BlogCategory.objects.create(name="Reviews")
        cls.review = BlogPost.objects.create(
            title="A Review of The Odyssey",
            subtitle="A review of The Odyssey",
            author=author,
            category=cat,
            post_date=datetime.date(2026, 7, 1),
            content="It was good.",
        )
        cls.showing.review = cls.review
        cls.showing.save(update_fields=["review"])

    def test_movie_page_links_to_our_review(self):
        html = self.client.get(f"/movies/{self.showing.slug}").content.decode()
        self.assertIn("Read our review", html)
        self.assertIn(f"/blog/{self.review.slug}", hrefs(html))

    def test_review_links_back_to_the_movie(self):
        html = self.client.get(f"/blog/{self.review.slug}").content.decode()
        self.assertIn(f"/movies/{self.showing.slug}", hrefs(html))


class InternalLinkingTests(MoviePageFixture):
    def test_homepage_links_to_now_showing_movie_pages(self):
        """Movie pages must not be orphaned — that's what kept the blog unindexed."""
        html = self.client.get("/").content.decode()
        self.assertIn(f"/movies/{self.showing.slug}", hrefs(html))

    def test_every_booked_film_reachable_by_link_following_from_home(self):
        seen, to_visit, visited = set(), ["/"], set()
        while to_visit:
            url = to_visit.pop()
            if url in visited:
                continue
            visited.add(url)
            resp = self.client.get(url)
            if resp.status_code != 200:
                continue
            for href in hrefs(resp.content.decode()):
                if href.startswith("/movies/"):
                    seen.add(href)
                elif href in ("/", "/classics/") and href not in visited:
                    to_visit.append(href)

        self.assertIn(f"/movies/{self.showing.slug}", seen)


class MovieStructuredDataTests(MoviePageFixture):
    def test_emits_movie_jsonld(self):
        html = self.client.get(f"/movies/{self.showing.slug}").content.decode()
        movie = movie_jsonld(html)
        self.assertIsNotNone(movie, "no Movie JSON-LD on the page")
        self.assertEqual(movie["name"], "The Odyssey")
        self.assertEqual(movie["duration"], "PT120M")
        self.assertEqual(movie["contentRating"], "PG-13")
        self.assertEqual(movie["sameAs"], "https://www.imdb.com/title/tt1234567/")
        self.assertEqual(movie["trailer"]["@type"], "VideoObject")

    def test_screening_event_per_upcoming_showtime_and_none_for_past(self):
        """Advertising a screening that already happened is wrong."""
        html = self.client.get(f"/movies/{self.showing.slug}").content.decode()
        events = movie_jsonld(html)["subjectOf"]
        self.assertEqual(len(events), 1)  # one future showtime; the past one excluded
        self.assertEqual(events[0]["@type"], "ScreeningEvent")
        self.assertEqual(
            events[0]["startDate"][:10],
            (timezone.localtime() + datetime.timedelta(days=1)).date().isoformat(),
        )
        self.assertEqual(events[0]["location"]["@type"], "MovieTheater")

    def test_archive_film_emits_movie_with_no_screening_events(self):
        html = self.client.get(f"/movies/{self.archived.slug}").content.decode()
        movie = movie_jsonld(html)
        self.assertIsNotNone(movie)
        self.assertNotIn("subjectOf", movie)

    def test_optional_fields_omitted_cleanly_when_blank(self):
        """A blank value is worse than an absent one."""
        movie = movie_jsonld(
            self.client.get(f"/movies/{self.archived.slug}").content.decode()
        )
        for absent in ("contentRating", "sameAs", "trailer"):
            self.assertNotIn(absent, movie)


class FilmSlugTests(TestCase):
    def test_slug_generated_from_title(self):
        film = Film.objects.create(title="The Odyssey")
        self.assertEqual(film.slug, "the-odyssey")

    def test_remake_gets_a_suffix_rather_than_raising(self):
        """Film has no release year, so remakes collide."""
        Film.objects.create(title="The Mummy")
        remake = Film.objects.create(title="The Mummy")
        self.assertEqual(remake.slug, "the-mummy-2")


class LinkFilmReviewsCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        cat = BlogCategory.objects.create(name="Reviews")
        cls.film = Film.objects.create(title="Project Hail Mary")
        cls.other = Film.objects.create(title="Unreviewed Film")
        cls.review = BlogPost.objects.create(
            title="A Review of Project Hail Mary",
            subtitle="A review of Project Hail Mary",
            author=author,
            category=cat,
            post_date=datetime.date(2026, 3, 23),
            content="...",
        )
        cls.not_a_review = BlogPost.objects.create(
            title="Our Autumn Plan",
            subtitle="Our autumn plan",
            author=author,
            category=cat,
            post_date=datetime.date(2025, 8, 10),
            content="...",
        )

    def run_command(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("link_film_reviews", *args, stdout=out)
        return out.getvalue()

    def test_links_review_shaped_titles_to_films(self):
        self.run_command()
        self.film.refresh_from_db()
        self.assertEqual(self.film.review, self.review)

    def test_leaves_unmatched_films_alone(self):
        self.run_command()
        self.other.refresh_from_db()
        self.assertIsNone(self.other.review)

    def test_dry_run_writes_nothing(self):
        self.run_command("--dry-run")
        self.film.refresh_from_db()
        self.assertIsNone(self.film.review)

    def test_never_overwrites_a_hand_made_link(self):
        self.film.review = self.not_a_review
        self.film.save(update_fields=["review"])
        self.run_command()
        self.film.refresh_from_db()
        self.assertEqual(self.film.review, self.not_a_review)
