from django.test import TestCase
from django.urls import reverse

from blog.models import BlogAuthor, BlogCategory, BlogPost


class BlogListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        for i in range(15):  # > 13, page 1's lead + paginate_by (12)
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
        self.assertIn("From the Booth: Blog | Fort Kent Cinema", html)   # title/og:title
        self.assertIn('class="blog-list-grid"', html)

    def test_heading_matches_the_home_page_section(self):
        html = self.client.get(reverse("blog_list")).content.decode()
        self.assertIn('<h1 class="blog-list-title">FROM THE BOOTH</h1>', html)
        self.assertIn("Film reviews and notes on running a small-town cinema.", html)

    def test_page_one_is_a_lead_and_a_grid_of_twelve(self):
        resp = self.client.get(reverse("blog_list"))
        self.assertEqual(len(resp.context["posts"]), 13)
        self.assertTrue(resp.context["page_obj"].has_next())
        # Newest first: the lead is the newest post, the grid the next twelve.
        self.assertEqual(resp.context["lead_post"].title, "Post 14")
        self.assertEqual(
            [p.title for p in resp.context["grid_posts"]],
            [f"Post {i}" for i in range(13, 1, -1)],
        )

    def test_lead_card_is_full_width_and_above_the_grid(self):
        html = self.client.get(reverse("blog_list")).content.decode()
        self.assertEqual(html.count("blog-card--feature"), 1)
        self.assertLess(html.index("blog-card--feature"), html.index('class="blog-list-grid"'))
        self.assertEqual(html.count('class="blog-card"'), 12)
        # The lead's title appears once: it is not repeated in the grid.
        self.assertEqual(html.count(">Post 14</h3>"), 1)

    def test_later_pages_are_the_grid_alone(self):
        resp = self.client.get(reverse("blog_list") + "?page=2")
        html = resp.content.decode()
        self.assertNotIn("blog-card--feature", html)
        self.assertEqual(html.count('class="blog-card"'), 2)
        self.assertIsNone(resp.context["lead_post"])
        self.assertEqual(
            [p.title for p in resp.context["grid_posts"]], ["Post 1", "Post 0"]
        )
        self.assertIn("Showing 14&ndash;15 of 15 posts", html)

    def test_page_one_counts_its_lead(self):
        html = self.client.get(reverse("blog_list")).content.decode()
        self.assertIn("Showing 1&ndash;13 of 15 posts", html)

    def test_only_one_post_is_a_lead_and_no_empty_grid(self):
        BlogPost.objects.exclude(title="Post 14").delete()
        html = self.client.get(reverse("blog_list")).content.decode()
        self.assertIn("blog-card--feature", html)
        self.assertNotIn('class="blog-list-grid"', html)
        self.assertNotIn('class="blog-pagination"', html)

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
    the page-1 boundary (13 posts with its lead card)."""

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
            for i in range(14)  # > 13 (page 1's lead + 12), all sharing one post_date
        ]

    def test_no_duplicates_or_skips_across_page_boundary(self):
        page1 = self.client.get(reverse("blog_list"))
        page2 = self.client.get(reverse("blog_list") + "?page=2")

        slugs_page1 = [p.slug for p in page1.context["page_obj"].object_list]
        slugs_page2 = [p.slug for p in page2.context["page_obj"].object_list]

        self.assertEqual(len(slugs_page1), 13)
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
        with self.assertNumQueries(3):
            # The post; related posts in its category, then the backfill.
            self.client.get(url)


class LeadPaginatorTests(TestCase):
    """Page 1 holds per_page + 1 (the lead card); every later page per_page."""

    def pages(self, count, per_page=12):
        from blog.site_views import LeadPaginator

        p = LeadPaginator(list(range(count)), per_page)
        return [
            (len(p.page(n).object_list), p.page(n).start_index(), p.page(n).end_index())
            for n in p.page_range
        ]

    def test_boundaries(self):
        self.assertEqual(self.pages(0), [(0, 0, 0)])
        self.assertEqual(self.pages(1), [(1, 1, 1)])
        self.assertEqual(self.pages(13), [(13, 1, 13)])
        self.assertEqual(self.pages(14), [(13, 1, 13), (1, 14, 14)])
        self.assertEqual(self.pages(25), [(13, 1, 13), (12, 14, 25)])
        self.assertEqual(
            self.pages(26), [(13, 1, 13), (12, 14, 25), (1, 26, 26)]
        )

    def test_every_item_appears_exactly_once(self):
        from blog.site_views import LeadPaginator

        for count in (0, 1, 12, 13, 14, 25, 26, 77):
            p = LeadPaginator(list(range(count)), 12)
            seen = [x for n in p.page_range for x in p.page(n).object_list]
            self.assertEqual(seen, list(range(count)), count)
