"""Blog indexability.

The blog had 77 posts and 9 indexed pages. Pagination was HTMX-only, so a
crawler running no JavaScript saw the first 6 posts and stopped — the other 71
had no inbound internal links at all, and Google filed them under "crawled,
currently not indexed".

These tests assert what a *crawler* sees: links, reachability, canonicals. They
never execute JavaScript, because neither does Googlebot when it first crawls.
"""

import datetime
import re

from blog.models import BlogAuthor, BlogCategory, BlogPost
from django.test import TestCase

PAGE_SIZE = 12


def make_posts(n, category, author, prefix="Post"):
    posts = []
    for i in range(n):
        posts.append(
            BlogPost.objects.create(
                title=f"{prefix} {i}",
                subtitle=f"{prefix} number {i}",
                author=author,
                category=category,
                post_date=datetime.date(2024, 1, 1) + datetime.timedelta(days=i),
                content="...",
            )
        )
    return posts


def hrefs(html):
    """Every href a crawler would follow. No JS, same as Googlebot's first pass."""
    return re.findall(r'<a[^>]+href="([^"]+)"', html)


class CrawlableFromBlogIndexTests(TestCase):
    """The regression test for the original bug."""

    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        category = BlogCategory.objects.create(name="Reviews")
        cls.posts = make_posts(77, category, author)

    def test_blog_index_links_to_page_two(self):
        html = self.client.get("/blog/").content.decode()
        self.assertIn("/blog/?page=2", hrefs(html))

    def test_pagination_is_not_javascript_only(self):
        """The original bug: paging existed only as an hx-get on a <div>."""
        html = self.client.get("/blog/").content.decode()
        self.assertNotIn("hx-trigger", html)
        self.assertNotIn("hx-get", html)

    def test_every_page_is_reachable_and_200s(self):
        expected_pages = -(-77 // PAGE_SIZE)  # ceil → 7
        for page in range(1, expected_pages + 1):
            resp = self.client.get("/blog/", {"page": page})
            self.assertEqual(resp.status_code, 200, f"page {page}")

    def test_all_77_posts_reachable_by_following_links_only(self):
        """Crawl the blog the way Googlebot would: follow <a href>, run no JS.
        Every post must be reachable, or it stays orphaned and unindexed."""
        seen_posts = set()
        to_visit = ["/blog/"]
        visited = set()

        while to_visit:
            url = to_visit.pop()
            if url in visited:
                continue
            visited.add(url)

            path, _, query = url.partition("?")
            params = dict(p.split("=") for p in query.split("&") if "=" in p)
            html = self.client.get(path, params).content.decode()

            for href in hrefs(html):
                if href.startswith("/blog/") and "?page=" in href:
                    if href not in visited:
                        to_visit.append(href)
                elif href.startswith("/blog/"):
                    seen_posts.add(href.rstrip("/"))

        expected = {f"/blog/{p.slug}" for p in self.posts}
        missing = expected - seen_posts
        self.assertEqual(
            missing, set(), f"{len(missing)} posts unreachable by link-following"
        )


class PaginationCanonicalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        category = BlogCategory.objects.create(name="Reviews")
        make_posts(30, category, author)

    def canonical(self, html):
        m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        return m.group(1) if m else None

    def test_page_one_canonicals_to_bare_blog_url(self):
        """Don't mint a ?page=1 duplicate."""
        html = self.client.get("/blog/").content.decode()
        self.assertTrue(self.canonical(html).endswith("/blog/"))

    def test_paginated_page_canonicals_to_itself(self):
        """Canonicalling page 2 to /blog/ tells Google to discard it and every
        link on it — which is how the posts got orphaned."""
        html = self.client.get("/blog/", {"page": 2}).content.decode()
        self.assertTrue(self.canonical(html).endswith("/blog/?page=2"))


def related_hrefs(html):
    """The hrefs inside the related-posts block only. The nav, back link and
    footer link to /blog/ on every post, so counting /blog/ hrefs page-wide
    passes even with the block gone."""
    m = re.search(r'<section class="blog-related".*?</section>', html, re.S)
    return hrefs(m.group(0)) if m else []


class RelatedPostsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        cls.reviews = BlogCategory.objects.create(name="Reviews")
        cls.news = BlogCategory.objects.create(name="News")
        cls.review_posts = make_posts(5, cls.reviews, cls.author, prefix="Review")
        # Newer than every review, so "most recent first" alone would pick
        # these. Preferring the same category has to beat that.
        cls.news_posts = [
            BlogPost.objects.create(
                title=f"News {i}",
                subtitle=f"News number {i}",
                author=cls.author,
                category=cls.news,
                post_date=datetime.date(2025, 1, 1) + datetime.timedelta(days=i),
                content="...",
            )
            for i in range(3)
        ]

    def test_post_detail_links_to_sibling_posts(self):
        post = self.review_posts[0]
        html = self.client.get(f"/blog/{post.slug}").content.decode()
        expected = [f"/blog/{p.slug}" for p in self.review_posts[4:1:-1]]
        self.assertEqual(related_hrefs(html), expected)

    def test_related_posts_exclude_the_post_itself(self):
        post = self.review_posts[0]
        related = self.client.get(f"/blog/{post.slug}").context["related_posts"]
        self.assertNotIn(post, related)

    def test_related_posts_prefer_same_category(self):
        """Not `all(...)` over the list: that passes on an empty one."""
        post = self.review_posts[0]
        related = self.client.get(f"/blog/{post.slug}").context["related_posts"]
        self.assertEqual(related, self.review_posts[4:1:-1])

    def test_thin_category_is_backfilled_with_other_posts(self):
        post = self.news_posts[0]
        related = self.client.get(f"/blog/{post.slug}").context["related_posts"]
        self.assertEqual(related, [*self.news_posts[2:0:-1], self.review_posts[4]])

    def test_related_posts_backfill_when_category_is_thin(self):
        """A lone post in its category must still get 3 related posts, or it
        stays orphaned."""
        lonely = BlogPost.objects.create(
            title="Only News Post",
            subtitle="The only news post",
            author=self.author,
            category=self.news,
            post_date=datetime.date(2024, 6, 1),
            content="...",
        )
        related = self.client.get(f"/blog/{lonely.slug}").context["related_posts"]
        self.assertEqual(len(related), 3)
        self.assertNotIn(lonely, related)
