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

    @mock.patch("blog.mixins.slugify")
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

    @mock.patch("blog.mixins.slugify")
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

    @mock.patch("blog.mixins.slugify")
    def test_slugify_is_called_on_save_if_no_slug(self, mock_slugify: Mock) -> None:
        mock_slugify.return_value = "slug"
        self.category.slug = None
        self.category.save()
        mock_slugify.assert_called_once_with(self.category.name)


class SlugFallbackTests(TestCase):
    """slugify() returns '' for text with no ASCII letters or digits. An empty
    slug made reverse('blog_detail') raise NoReverseMatch on every page that
    links to the post: /blog/, the sitemap, related cards, the film page."""

    def setUp(self) -> None:
        self.author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        self.category = BlogCategory.objects.create(name="News")

    def make_post(self, subtitle: str) -> BlogPost:
        return BlogPost.objects.create(
            title="Rating",
            subtitle=subtitle,
            author=self.author,
            category=self.category,
            content="...",
            post_date="2025-01-01",
        )

    def test_unsluggable_subtitle_falls_back_to_a_unique_slug(self) -> None:
        first = self.make_post("★★★★☆")
        second = self.make_post("Кино")
        self.assertEqual(first.slug, "post")
        self.assertEqual(second.slug, "post-2")
        self.assertEqual(self.client.get("/blog/").status_code, 200)
        self.assertEqual(self.client.get(first.get_absolute_url()).status_code, 200)

    def test_unsluggable_author_and_category_names_fall_back(self) -> None:
        self.assertEqual(BlogAuthor.objects.create(first_name="🎬", last_name="").slug, "author")
        self.assertEqual(BlogCategory.objects.create(name="Кино").slug, "category")
