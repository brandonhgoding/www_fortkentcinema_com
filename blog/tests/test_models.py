from unittest import mock
from unittest.mock import Mock

from blog.models import BlogAuthor, BlogCategory, BlogPost
from django.test import TestCase


class BlogPostTestCase(TestCase):
    def setUp(self) -> None:
        self.author = BlogAuthor.objects.create(
            last_name="last_name", first_name="first_name"
        )
        self.category = BlogCategory.objects.create(name="title")
        self.post = BlogPost.objects.create(
            title="title",
            subtitle="subtitle",
            author=self.author,
            category=self.category,
            content="content",
            post_date="2025-01-01",
        )

    def test_str(self) -> None:
        self.assertEqual(str(self.post), self.post.subtitle)

    @mock.patch("core.mixins.slugify")
    def test_slugify_is_called_on_save_if_no_slug(self, mock_slugify: Mock) -> None:
        mock_slugify.return_value = "slug"
        self.post.slug = None
        self.post.save()
        mock_slugify.assert_called_once_with(self.post.subtitle)


class BlogAuthorTestCase(TestCase):
    def setUp(self) -> None:
        self.author = BlogAuthor.objects.create(
            last_name="last_name", first_name="first_name"
        )

    def test_str(self) -> None:
        self.assertEqual(
            str(self.author), f"{self.author.first_name} {self.author.last_name}"
        )

    @mock.patch("core.mixins.slugify")
    def test_slugify_is_called_on_save_if_no_slug(self, mock_slugify: Mock) -> None:
        mock_slugify.return_value = "slug"
        self.author.slug = None
        self.author.save()
        mock_slugify.assert_called_once_with(self.author.full_name)


class BlogCategoryTestCase(TestCase):
    def setUp(self) -> None:
        self.category = BlogCategory.objects.create(name="title")

    def test_str(self) -> None:
        self.assertEqual(str(self.category), f"{self.category.name}")

    @mock.patch("core.mixins.slugify")
    def test_slugify_is_called_on_save_if_no_slug(self, mock_slugify: Mock) -> None:
        mock_slugify.return_value = "slug"
        self.category.slug = None
        self.category.save()
        mock_slugify.assert_called_once_with(self.category.name)
