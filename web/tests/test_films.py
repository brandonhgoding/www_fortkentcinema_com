"""Film slugs, the review-linking command, and the guard that nothing on the
site still points at the retired /movies/<slug> pages.

The pages were retired 2026-10-14: on-site they duplicated the home cards
(poster, synopsis, trailer, times) and off-site their archive state was thin
content advertised at sitemap priority 0.8. The slugs stay on the model —
they are harmless, and the legacy redirect still reads them.
"""

import datetime
import re

from blog.models import BlogAuthor, BlogCategory, BlogPost
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.test import TestCase
from django.utils import timezone


def hrefs(html):
    return re.findall(r'<a[^>]+href="([^"]+)"', html)


class NoFilmPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        screen = Screen.objects.create(name="Screen 1", capacity=100)
        cls.film = Film.objects.create(
            title="The Odyssey",
            runtime_minutes=120,
            poster_url="https://image.tmdb.org/t/p/w500/odyssey.jpg",
        )
        today = timezone.localdate()
        eng = Engagement.objects.create(
            screen=screen,
            start_date=today,
            end_date=today + datetime.timedelta(days=6),
            status="CONFIRMED",
        )
        EngagementFilm.objects.create(engagement=eng, film=cls.film, position=0)
        Showtime.objects.create(
            engagement=eng,
            screen=screen,
            starts_at=timezone.now() + datetime.timedelta(days=1, hours=2),
        )
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
        cls.film.review = cls.review
        cls.film.save(update_fields=["review"])

    def test_home_does_not_link_to_a_film_page(self):
        html = self.client.get("/").content.decode()
        self.assertIn("The Odyssey", html)
        self.assertFalse([h for h in hrefs(html) if h.startswith("/movies/")])
        self.assertNotIn("/movies/", html)  # nor in the JSON-LD

    def test_review_does_not_link_to_a_film_page(self):
        html = self.client.get(f"/blog/{self.review.slug}").content.decode()
        self.assertNotIn("/movies/", html)

    def test_sitemap_lists_no_film_pages(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("/movies/", xml)

    def test_film_has_no_public_url(self):
        self.assertFalse(hasattr(Film, "get_absolute_url"))


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
    """Fixtures mirror PRODUCTION, which the first version of this command did not.

    A post's `title` is an editorial headline — the film's name is in the
    `subtitle`, wrapped in typographic quotes. Matching on `title` (which the
    first cut did) finds nothing, and silently: the command reported "linked 0"
    and looked like it had simply found no matches.
    """

    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        cat = BlogCategory.objects.create(name="Reviews")
        cls.film = Film.objects.create(title="Project Hail Mary")
        cls.other = Film.objects.create(title="Unreviewed Film")

        # Real shape: headline title, film name in a smart-quoted subtitle.
        # slug derives from subtitle -> "a-review-of-project-hail-mary".
        cls.review = BlogPost.objects.create(
            title="Connecting The Dots",
            subtitle="A Review of “Project Hail Mary”",
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

    def test_fixture_matches_production_shape(self):
        """Guard the guard: if the slug stops deriving from the subtitle, the
        command's whole premise breaks and these tests must fail loudly."""
        self.assertEqual(self.review.slug, "a-review-of-project-hail-mary")
        self.assertNotIn("review", self.review.title.lower())

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

    def make_review(self, subtitle, post_date, **extra):
        return BlogPost.objects.create(
            title="Another Take",
            subtitle=subtitle,
            author=self.review.author,
            category=self.review.category,
            post_date=post_date,
            content="...",
            **extra,
        )

    def test_draft_reviews_are_not_linked(self):
        """A draft 404s publicly, so the film page must not link to it."""
        film = Film.objects.create(title="Unfinished")
        self.make_review(
            "A Review of Unfinished", datetime.date(2026, 4, 1),
            status=BlogPost.Status.DRAFT,
        )
        self.run_command()
        film.refresh_from_db()
        self.assertIsNone(film.review)

    def test_newest_published_review_wins(self):
        """Two reviews of one film: the film was linked once per match, and
        the oldest write survived — even when it was a draft."""
        film = Film.objects.create(title="Rewatched")
        self.make_review("A Review of Rewatched", datetime.date(2024, 1, 1))
        newest = self.make_review("A Preview of Rewatched", datetime.date(2026, 1, 1))
        self.make_review(
            "An Appreciation of Rewatched", datetime.date(2026, 6, 1),
            status=BlogPost.Status.DRAFT,
        )
        out = self.run_command()
        film.refresh_from_db()
        self.assertEqual(film.review, newest)
        self.assertEqual(out.count("Rewatched  ->"), 1)

    def test_no_match_hint_does_not_point_at_admin(self):
        """FilmAdmin.review is read-only; links are made in the post editor."""
        Film.objects.filter(pk=self.film.pk).update(review=self.not_a_review)
        out = self.run_command()
        self.assertNotIn("admin", out)
        self.assertIn("dashboard", out)

    def test_never_overwrites_a_hand_made_link(self):
        self.film.review = self.not_a_review
        self.film.save(update_fields=["review"])
        self.run_command()
        self.film.refresh_from_db()
        self.assertEqual(self.film.review, self.not_a_review)
