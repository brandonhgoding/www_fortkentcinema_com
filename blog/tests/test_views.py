"""The posts API is read-only. Posts are written in the dashboard."""

import base64
import datetime

from django.test import Client, TestCase

from accounts.tests.factories import make_user
from blog.models import BlogAuthor, BlogCategory, BlogPost


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
        make_user(email="s@example.com", password="pw12345", is_staff=True)
        self.client.login(username="s@example.com", password="pw12345")

    def test_reads_work(self):
        self.assertEqual(self.client.get("/api/posts/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/posts/{self.post.slug}/").status_code, 200)

    def test_credentials_are_ignored_not_checked(self):
        """The API is public and read-only, so it must not check passwords.
        DRF's default stack included HTTP Basic auth, which turned a
        cookie-less GET with a bad Authorization header into a 403 and a
        good one into a 200: a password-guessing oracle beside the login
        form, with none of its protection."""
        guess = "Basic " + base64.b64encode(b"admin:hunter2").decode()
        anonymous = Client()  # no session, or session auth would win first
        response = anonymous.get("/api/posts/", HTTP_AUTHORIZATION=guess)
        self.assertEqual(response.status_code, 200)

    def test_writes_are_not_allowed(self):
        # 403: the API authenticates nobody, so even this staff session is
        # anonymous here and the permission class refuses before the
        # read-only viewset would have answered 405.
        detail = f"/api/posts/{self.post.slug}/"
        self.assertEqual(self.client.post("/api/posts/", {"title": "x"}).status_code, 403)
        self.assertEqual(
            self.client.patch(detail, {"title": "x"}, content_type="application/json").status_code,
            403,
        )
        self.assertEqual(self.client.delete(detail).status_code, 403)
        self.assertTrue(BlogPost.objects.filter(pk=self.post.pk).exists())


class PostApiListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cls.cat = BlogCategory.objects.create(name="News")
        # All on one day, so post_date alone leaves their order to the database.
        cls.posts = cls.make_posts(13)

    @classmethod
    def make_posts(cls, n, prefix="same-day"):
        return [
            BlogPost.objects.create(
                title=f"Post {i}", subtitle=f"{prefix}-{i}", author=cls.author,
                category=cls.cat, post_date=datetime.date(2026, 5, 1), content="Body.",
            )
            for i in range(n)
        ]

    def test_same_day_posts_page_in_a_stable_order(self):
        """Without an -id tiebreaker Postgres may order the tied rows
        differently for each LIMIT/OFFSET query, skipping or repeating posts
        across pages."""
        ids = []
        for offset in range(0, 13, 6):
            data = self.client.get("/api/posts/", {"limit": 6, "offset": offset}).json()
            ids += [r["id"] for r in data["results"]]
        self.assertEqual(ids, sorted((str(p.id) for p in self.posts), reverse=True))

    def test_list_does_not_query_per_post(self):
        # The COUNT, then one page with author and category joined in.
        with self.assertNumQueries(2):
            self.client.get("/api/posts/", {"limit": 13})

    def test_limit_is_capped_at_fifty(self):
        self.make_posts(40, prefix="more")
        data = self.client.get("/api/posts/", {"limit": 10_000}).json()
        self.assertEqual(data["count"], 53)
        self.assertEqual(len(data["results"]), 50)
