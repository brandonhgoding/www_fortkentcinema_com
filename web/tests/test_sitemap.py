from django.test import TestCase
from blog.models import BlogAuthor, BlogCategory, BlogPost


class SitemapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        a = BlogAuthor.objects.create(first_name="A", last_name="B")
        c = BlogCategory.objects.create(name="News")
        cls.post = BlogPost.objects.create(title="P1", subtitle="p-one", author=a,
                                           category=c, post_date="2026-01-01", content="x")

    def test_sitemap_lists_static_and_posts(self):
        resp = self.client.get("/sitemap.xml")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "application/xml")
        body = resp.content.decode()
        self.assertIn("/rentals/", body)
        self.assertIn("/blog/", body)
        self.assertIn(f"/blog/{self.post.slug}", body)

    def test_robots_txt(self):
        resp = self.client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "text/plain")
        self.assertIn("Sitemap:", resp.content.decode())

    def test_blogpost_get_absolute_url(self):
        self.assertEqual(self.post.get_absolute_url(), f"/blog/{self.post.slug}")
