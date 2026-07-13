"""Legacy URL redirects.

Earlier generations of fortkentcinema.com used different URL structures. Google
still holds those URLs (they were 404ing after the Django migration), so every
one of them must 301 to its modern equivalent rather than die.
"""

import datetime

from blog.models import BlogAuthor, BlogCategory, BlogPost
from django.test import TestCase


class LegacyBlogRedirectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        category = BlogCategory.objects.create(name="Reviews")
        # slug auto-derives from subtitle (BlogPost.slug_field)
        cls.post = BlogPost.objects.create(
            title="Bullet Train",
            subtitle="A Review of Bullet Train",
            author=author,
            category=category,
            post_date=datetime.date(2022, 8, 6),
            content="...",
        )

    def test_legacy_post_url_redirects_to_modern_post(self):
        resp = self.client.get("/fort-kent-cinema-blog/a-review-of-bullet-train/")
        self.assertRedirects(
            resp,
            "/blog/a-review-of-bullet-train",
            status_code=301,
            target_status_code=200,
        )

    def test_legacy_post_url_without_trailing_slash_also_redirects(self):
        """Google holds the trailing-slash form, but don't rely on APPEND_SLASH
        to bounce the bare form through a second hop."""
        resp = self.client.get("/fort-kent-cinema-blog/a-review-of-bullet-train")
        self.assertRedirects(
            resp,
            "/blog/a-review-of-bullet-train",
            status_code=301,
            target_status_code=200,
        )

    def test_legacy_blog_index_redirects_to_blog_list(self):
        resp = self.client.get("/fort-kent-cinema-blog/")
        self.assertRedirects(resp, "/blog/", status_code=301, target_status_code=200)

    def test_redirect_is_a_single_hop(self):
        """A 301 chain leaks the equity we're trying to recover."""
        resp = self.client.get(
            "/fort-kent-cinema-blog/a-review-of-bullet-train/", follow=True
        )
        self.assertEqual(len(resp.redirect_chain), 1)
        self.assertEqual(resp.status_code, 200)

    def test_legacy_url_for_unknown_slug_still_redirects(self):
        """We redirect on URL shape, not on post existence — the modern blog
        route can 404 on its own if the post is genuinely gone."""
        resp = self.client.get("/fort-kent-cinema-blog/a-post-that-never-existed/")
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp["Location"], "/blog/a-post-that-never-existed")


class LegacyPageRedirectTests(TestCase):
    def test_coming_soon_redirects_to_homepage_section(self):
        """/coming-soon/ was 404ing while still drawing ~1,590 impressions at
        position 5.2 — the site's best-ranking non-homepage URL."""
        resp = self.client.get("/coming-soon/")
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp["Location"], "/#coming-soon")

    def test_coming_soon_without_trailing_slash_redirects(self):
        resp = self.client.get("/coming-soon")
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp["Location"], "/#coming-soon")

    def test_legacy_contact_redirects_home(self):
        """No modern contact page; address and phone live in the homepage footer."""
        resp = self.client.get("/contact-fort-kent-cinema/")
        self.assertRedirects(resp, "/", status_code=301, target_status_code=200)

    def test_legacy_archive_movie_redirects_home(self):
        """The old per-movie pages. Re-point these at /movies/<slug> once real
        per-movie pages exist."""
        resp = self.client.get("/archive/karate-kid-legends")
        self.assertRedirects(resp, "/", status_code=301, target_status_code=200)

    def test_legacy_archive_index_redirects_home(self):
        resp = self.client.get("/archive/")
        self.assertRedirects(resp, "/", status_code=301, target_status_code=200)


class LegacyRedirectsDoNotShadowLiveRoutesTests(TestCase):
    def test_modern_blog_routes_still_resolve(self):
        self.assertEqual(self.client.get("/blog/").status_code, 200)

    def test_homepage_still_resolves(self):
        self.assertEqual(self.client.get("/").status_code, 200)
