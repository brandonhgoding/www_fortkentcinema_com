from django.test import TestCase
from django.urls import reverse

from blog.models import BlogAuthor, BlogCategory, BlogPost


class BlogListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        for i in range(15):  # > paginate_by (12)
            BlogPost.objects.create(
                title=f"Post {i}", subtitle=f"sub-{i}", author=author, category=cat,
                post_date=f"2026-01-{i+1:02d}",
                content=f"Body paragraph for post {i}.",
            )

    def test_list_200_and_template(self):
        resp = self.client.get(reverse("blog_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "blog/post_list.html")
        self.assertTemplateUsed(resp, "base.html")

    def test_list_meta(self):
        html = self.client.get(reverse("blog_list")).content.decode()
        self.assertIn("Blog | Fort Kent Cinema", html)   # title/og:title
        self.assertIn('class="blog-list-grid"', html)

    def test_paginates_twelve(self):
        resp = self.client.get(reverse("blog_list"))
        self.assertEqual(len(resp.context["posts"]), 12)
        self.assertTrue(resp.context["page_obj"].has_next())

    def test_renders_a_crawlable_pagination_nav(self):
        """Paging must be plain links. It was an HTMX `hx-trigger="revealed"`
        sentinel, which hid 71 of 77 posts from Googlebot."""
        html = self.client.get(reverse("blog_list")).content.decode()
        self.assertIn('class="blog-pagination"', html)
        self.assertIn('href="/blog/?page=2"', html)


class BlogListEmptyTests(TestCase):
    def test_no_published_posts_shows_an_empty_state(self):
        """It rendered an empty grid and "Showing 0–0 of 0 posts"."""
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        BlogPost.objects.create(
            title="Draft", subtitle="draft", author=author, category=cat,
            post_date="2026-01-01", content="...", status=BlogPost.Status.DRAFT,
        )
        html = self.client.get(reverse("blog_list")).content.decode()
        self.assertIn('class="blog-empty"', html)
        self.assertNotIn("of 0 posts", html)
        self.assertNotIn('class="blog-list-grid"', html)


class BlogListSameDatePaginationTests(TestCase):
    """Regression test for undefined ordering when many posts share a
    day-granular post_date: without a unique tiebreaker (-id), the DB is
    free to return that tied group in a different relative order for the
    page-1 vs page-2 query, causing cards to be duplicated or skipped at
    the 12-per-page boundary."""

    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        cls.posts = [
            BlogPost.objects.create(
                title=f"Same Date Post {i}", subtitle=f"sub-{i}",
                author=author, category=cat, post_date="2026-05-01",
                content=f"Body paragraph for post {i}.",
            )
            for i in range(13)  # > paginate_by (12), all sharing one post_date
        ]

    def test_no_duplicates_or_skips_across_page_boundary(self):
        page1 = self.client.get(reverse("blog_list"))
        page2 = self.client.get(reverse("blog_list") + "?page=2")

        slugs_page1 = [p.slug for p in page1.context["page_obj"].object_list]
        slugs_page2 = [p.slug for p in page2.context["page_obj"].object_list]

        self.assertEqual(len(slugs_page1), 12)
        self.assertEqual(len(slugs_page2), 1)

        # No slug should appear on both pages.
        self.assertEqual(set(slugs_page1) & set(slugs_page2), set())

        # Union of both pages must cover every created post (none skipped).
        all_slugs = set(slugs_page1) | set(slugs_page2)
        expected_slugs = {p.slug for p in self.posts}
        self.assertEqual(all_slugs, expected_slugs)


class BlogDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        cls.post = BlogPost.objects.create(
            title="Big News", subtitle="A subtitle that describes it",
            author=author, category=cat, post_date="2026-01-15",
            content="First paragraph.\n\nSecond paragraph.",
        )

    def test_detail_200_and_template(self):
        resp = self.client.get(reverse("blog_detail", args=[self.post.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "blog/post_detail.html")

    def test_unknown_slug_404(self):
        self.assertEqual(self.client.get(reverse("blog_detail", args=["nope"])).status_code, 404)

    def test_per_post_meta_overrides(self):
        html = self.client.get(reverse("blog_detail", args=[self.post.slug])).content.decode()
        self.assertIn("<title>Big News | Fort Kent Cinema</title>", html)
        self.assertIn('property="og:title" content="Big News"', html)
        self.assertIn('property="og:type" content="article"', html)
        # description falls back to the subtitle
        self.assertIn('property="og:description" content="A subtitle that describes it"', html)

    def test_content_renders_paragraphs(self):
        html = self.client.get(reverse("blog_detail", args=[self.post.slug])).content.decode()
        self.assertIn("<p>First paragraph.</p>", html)
        self.assertIn("<p>Second paragraph.</p>", html)

    def test_trailing_slash_redirects_to_canonical_url(self):
        """/blog/<slug>/ used to 404. People and other sites add the slash."""
        resp = self.client.get(f"/blog/{self.post.slug}/")
        self.assertRedirects(
            resp, f"/blog/{self.post.slug}", status_code=301, target_status_code=200
        )

    def test_detail_query_count(self):
        """The post's author and category are joined into the post's own query
        rather than fetched one by one while the template renders."""
        url = reverse("blog_detail", args=[self.post.slug])
        self.client.get(url)  # warm the site-config cache
        with self.assertNumQueries(4):
            # The post; related posts in its category, then the backfill; its films.
            self.client.get(url)
