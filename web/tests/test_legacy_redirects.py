"""Legacy URL redirects.

Earlier generations of fortkentcinema.com used different URL structures. Google
still holds those URLs (they were 404ing after the Django migration), so every
one of them must 301 to its modern equivalent rather than die.
"""

from django.test import TestCase


class LegacyBlogRedirectTests(TestCase):
    """The blog was discontinued 2026-11-01. Its current addresses and the
    older /fort-kent-cinema-blog/ ones all go home in one hop."""

    def test_blog_addresses_redirect_home(self):
        for path in (
            "/blog/",
            "/blog",
            "/blog/a-review-of-bullet-train",
            "/blog/a-review-of-bullet-train/",
            "/blog/category/reviews/",
            "/blog/?page=2",
            "/fort-kent-cinema-blog/",
            "/fort-kent-cinema-blog/a-review-of-bullet-train/",
            "/fort-kent-cinema-blog/кино/",
        ):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertRedirects(
                    resp, "/", status_code=301, target_status_code=200
                )

    def test_a_lookalike_path_is_not_swallowed(self):
        self.assertEqual(self.client.get("/blogger/").status_code, 404)


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

    def test_removed_info_pages_redirect_home(self):
        """Heckle Night, Open Mic and History, removed 2026-11-01."""
        for path in ("/heckle-night/", "/open-mic/", "/history/", "/history"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertRedirects(resp, "/", status_code=301, target_status_code=200)

    def test_legacy_archive_movie_redirects_home(self):
        """The 2022-era per-movie pages."""
        resp = self.client.get("/archive/karate-kid-legends")
        self.assertRedirects(resp, "/", status_code=301, target_status_code=200)

    def test_movie_page_redirects_home(self):
        """/movies/<slug> was retired 2026-10-14. The home page carries every
        showtime the film page did, so that is where the links go; the slugs
        were in the sitemap for months and must not 404."""
        for path in ("/movies/the-odyssey", "/movies/the-odyssey/"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertRedirects(
                    resp, "/", status_code=301, target_status_code=200
                )

    def test_legacy_archive_index_redirects_home(self):
        resp = self.client.get("/archive/")
        self.assertRedirects(resp, "/", status_code=301, target_status_code=200)

    def test_classics_redirects_home(self):
        """Classic Movie Night was discontinued 2026-08-14. /classics/ carried
        its own ranking history, so it redirects rather than 404s."""
        resp = self.client.get("/classics/")
        self.assertRedirects(resp, "/", status_code=301, target_status_code=200)

    def test_classics_without_trailing_slash_redirects(self):
        resp = self.client.get("/classics")
        self.assertRedirects(resp, "/", status_code=301, target_status_code=200)

    def test_retired_event_page_redirects_home(self):
        """The Silents Synced screening played 2026-09-01 and its page came down
        the same day. It was in the sitemap, so the URL must not 404."""
        resp = self.client.get("/events/silents-synced-a-woman-of-the-world")
        self.assertRedirects(resp, "/", status_code=301, target_status_code=200)

    def test_retired_event_page_with_trailing_slash_redirects(self):
        resp = self.client.get("/events/silents-synced-a-woman-of-the-world/")
        self.assertRedirects(resp, "/", status_code=301, target_status_code=200)

    def test_vote_pages_redirect_home(self):
        """The film vote was retired 2026-10-31. /vote and the past rounds'
        /vote/<slug> pages were in the sitemap, so they must not 404."""
        for path in ("/vote", "/vote/", "/vote/october-picks", "/vote/october-picks/"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertRedirects(
                    resp, "/", status_code=301, target_status_code=200
                )

    def test_thanks_page_redirects_home(self):
        """/thanks was Square's post-payment landing; nothing is paid for on
        the site any more, but an old Square link may still send someone."""
        for path in ("/thanks", "/thanks/", "/thanks?tier=individual"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertRedirects(
                    resp, "/", status_code=301, target_status_code=200
                )

    def test_membership_pages_redirect_home(self):
        """Online membership checkout was retired 2026-10-31 (join pages were
        linked from every tier card, order pages from welcome emails) and
        /membership/ itself on 2026-11-01."""
        for path in (
            "/membership/",
            "/membership",
            "/membership/join/individual/",
            "/membership/join/individual",
            "/membership/order/abc123DEF_-x/",
        ):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertRedirects(
                    resp, "/", status_code=301, target_status_code=200
                )


class LegacyRedirectsDoNotShadowLiveRoutesTests(TestCase):
    def test_homepage_still_resolves(self):
        self.assertEqual(self.client.get("/").status_code, 200)
