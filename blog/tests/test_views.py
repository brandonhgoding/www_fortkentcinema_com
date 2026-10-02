"""The posts API is read-only. Posts are written in the dashboard."""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from blog.models import BlogAuthor, BlogCategory, BlogPost

User = get_user_model()


class ReadOnlyApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        cls.post = BlogPost.objects.create(
            title="Post", subtitle="a-post", author=author, category=cat,
            post_date=datetime.date(2026, 1, 1), content="Body.",
        )

    def setUp(self):
        # Even staff: the old ModelViewSet let any logged-in account write.
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_reads_work(self):
        self.assertEqual(self.client.get("/api/posts/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/posts/{self.post.slug}/").status_code, 200)

    def test_writes_are_not_allowed(self):
        detail = f"/api/posts/{self.post.slug}/"
        self.assertEqual(self.client.post("/api/posts/", {"title": "x"}).status_code, 405)
        self.assertEqual(
            self.client.patch(detail, {"title": "x"}, content_type="application/json").status_code,
            405,
        )
        self.assertEqual(self.client.delete(detail).status_code, 405)
        self.assertTrue(BlogPost.objects.filter(pk=self.post.pk).exists())
