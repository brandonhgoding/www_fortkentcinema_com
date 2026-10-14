"""Film slugs, and the guard that nothing on the site still points at the
retired /movies/<slug> pages.

The pages were retired 2026-10-14: on-site they duplicated the home cards
(poster, synopsis, trailer, times) and off-site their archive state was thin
content advertised at sitemap priority 0.8. The slugs stay on the model —
they are harmless, and the legacy redirect still reads them. The film-to-review
link that fed the page's "Read our review" went the same day, along with the
command that filled it.
"""

import datetime
import re

from blog.models import BlogAuthor, BlogCategory, BlogPost
from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.core.management import call_command
from django.core.management.base import CommandError
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

    def test_film_has_no_review_link(self):
        self.assertNotIn("review", {f.name for f in Film._meta.get_fields()})
        with self.assertRaises(CommandError):
            call_command("link_film_reviews")


class FilmSlugTests(TestCase):
    def test_slug_generated_from_title(self):
        film = Film.objects.create(title="The Odyssey")
        self.assertEqual(film.slug, "the-odyssey")

    def test_remake_gets_a_suffix_rather_than_raising(self):
        """Film has no release year, so remakes collide."""
        Film.objects.create(title="The Mummy")
        remake = Film.objects.create(title="The Mummy")
        self.assertEqual(remake.slug, "the-mummy-2")
