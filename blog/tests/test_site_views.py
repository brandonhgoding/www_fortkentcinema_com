from django.test import TestCase
from django.urls import reverse

from blog.models import BlogAuthor, BlogCategory, BlogPost


class BlogListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        for i in range(8):  # > paginate_by (6)
            BlogPost.objects.create(
                title=f"Post {i}", subtitle=f"sub-{i}", author=author, category=cat,
                post_date=f"2026-01-0{i+1}" if i < 9 else "2026-02-01",
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

    def test_paginates_six(self):
        resp = self.client.get(reverse("blog_list"))
        self.assertEqual(len(resp.context["posts"]), 6)
        self.assertTrue(resp.context["page_obj"].has_next())

    def test_htmx_returns_fragment_only(self):
        resp = self.client.get(reverse("blog_list") + "?page=2", HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(resp, "blog/_post_cards.html")
        self.assertTemplateNotUsed(resp, "base.html")     # fragment, not full page
        html = resp.content.decode()
        self.assertIn("blog-list-card-link", html)
        # Literal template text isn't autoescaped by Django (only variable
        # output is), so the apostrophe renders as-is rather than an entity.
        self.assertIn("You've reached the end", html)  # page 2 is last (8 posts, 6/page)
