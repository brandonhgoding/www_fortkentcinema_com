"""Drafts stay off every public surface: the blog, the home teaser, the
sitemap, the API and film pages. Staff see them only in the dashboard."""

import datetime

from django.test import TestCase
from django.urls import reverse

from blog.models import BlogAuthor, BlogCategory, BlogPost


class DraftVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        cls.live = BlogPost.objects.create(
            title="Live Post", subtitle="live-post", author=author, category=cat,
            post_date=datetime.date(2026, 1, 1), content="Out in the world.",
        )
        cls.draft = BlogPost.objects.create(
            title="Secret Draft", subtitle="secret-draft", author=author, category=cat,
            post_date=datetime.date(2026, 1, 2), content="Not yet.",
            status=BlogPost.Status.DRAFT,
        )

    def test_published_queryset(self):
        self.assertEqual(list(BlogPost.objects.published()), [self.live])
        self.assertEqual(BlogPost.objects.count(), 2)

    def test_new_rows_default_to_published(self):
        """Rows made outside the dashboard keep working as they always did."""
        self.assertTrue(self.live.is_published)
        self.assertFalse(self.draft.is_published)

    def test_blog_list_hides_drafts(self):
        html = self.client.get(reverse("blog_list")).content.decode()
        self.assertIn("Live Post", html)
        self.assertNotIn("Secret Draft", html)

    def test_draft_detail_404s(self):
        resp = self.client.get(reverse("blog_detail", args=[self.draft.slug]))
        self.assertEqual(resp.status_code, 404)

    def test_draft_is_never_a_related_post(self):
        resp = self.client.get(reverse("blog_detail", args=[self.live.slug]))
        self.assertNotIn(self.draft, resp.context["related_posts"])

    def test_home_teaser_hides_drafts(self):
        resp = self.client.get("/")
        self.assertNotIn(self.draft, list(resp.context["recent_posts"]))

    def test_sitemap_hides_drafts(self):
        body = self.client.get("/sitemap.xml").content.decode()
        self.assertIn(f"/blog/{self.live.slug}", body)
        self.assertNotIn(f"/blog/{self.draft.slug}", body)

    def test_api_hides_drafts(self):
        resp = self.client.get("/api/posts/")
        slugs = [p["slug"] for p in resp.json()["results"]]
        self.assertEqual(slugs, [self.live.slug])
        self.assertEqual(self.client.get(f"/api/posts/{self.draft.slug}/").status_code, 404)
