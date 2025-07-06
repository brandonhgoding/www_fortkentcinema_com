import json

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient


class BlogPostListAPIViewTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.fixtures = json.load(open("blog/fixtures/blog.json"))

    def test_blog_post_list_returns_posts(self) -> None:
        url = reverse("blog-post-list")  # Replace with your actual URL name
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], len(self.fixtures))  # type: ignore[attr-defined]
