"""Blog header image uploads.

Uploads were 404ing the moment they were made, and vanishing on the next deploy.

Root cause: MEDIA_ROOT was hardcoded to BASE_DIR / "media", i.e. *inside the
release directory*. On the app serving www.fortkentcinema.com, ansible's media
symlink task is guarded by

    when: app.media_root is search(app.dest ~ '/shared/')

and that app's media_root points at the OTHER app's shared dir, so the guard
silently skipped and no symlink was made. Django wrote uploads into
  fortkentcinema_www/releases/<ts>/media/
while nginx served /media/ from
  api_fortkentcinema_com/shared/media/
Two different directories. Worse, each deploy rsyncs the repo over a fresh
release dir, so the upload was stranded in the previous release.

MEDIA_ROOT is now read from the environment, so ansible points Django at exactly
the directory nginx serves, and there is no symlink left to silently miss.
"""

import shutil
import tempfile
from pathlib import Path

from blog.models import BlogAuthor, BlogCategory, BlogPost
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

# A minimal valid PNG (1x1). ImageField validates that the file is a real image.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class MediaRootTests(TestCase):
    def test_media_root_is_environment_configurable(self):
        """It was BASE_DIR / "media" — inside the release directory, which the
        next deploy replaces. Production points this at the shared dir nginx
        actually serves."""
        from fortkentcinema import settings as s

        src = Path(s.__file__).read_text()
        self.assertIn('config("MEDIA_ROOT"', src)
        self.assertNotIn('MEDIA_ROOT = BASE_DIR / "media"', src)


class HeaderImageNamingTests(TestCase):
    """Uploads should be named for the post's slug, not whatever the file was
    called on the author's desktop (`ChatGPT_Image_Jul_11_2026_at_05_21_01_PM.png`)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        self.cat = BlogCategory.objects.create(name="Reviews")

    def make_post(self, subtitle, filename="ChatGPT_Image_Jul_11_2026.png", content=PNG):
        return BlogPost.objects.create(
            title="Connecting The Dots",
            subtitle=subtitle,
            author=self.author,
            category=self.cat,
            post_date="2026-07-11",
            content="...",
            header_image=SimpleUploadedFile(filename, content, content_type="image/png"),
        )

    def test_upload_is_renamed_to_the_post_slug(self):
        with override_settings(MEDIA_ROOT=self._tmp):
            post = self.make_post('A Review of "Project Hail Mary"')
        self.assertEqual(post.slug, "a-review-of-project-hail-mary")
        self.assertEqual(
            post.header_image.name, "blog/images/a-review-of-project-hail-mary.png"
        )

    def test_extension_is_preserved_and_lowercased(self):
        with override_settings(MEDIA_ROOT=self._tmp):
            post = self.make_post("A Review of Thing", filename="PHOTO.JPEG", content=PNG)
        self.assertTrue(post.header_image.name.endswith(".jpeg"))

    def test_reupload_overwrites_rather_than_suffixing(self):
        """Django's default storage would name the second file
        `a-review-of-thing_Ab3xY.png`, which defeats the whole point."""
        with override_settings(MEDIA_ROOT=self._tmp):
            post = self.make_post("A Review of Thing")
            first = post.header_image.name

            post.header_image = SimpleUploadedFile("other.png", PNG, content_type="image/png")
            post.save()
            post.refresh_from_db()

        self.assertEqual(post.header_image.name, first)
        self.assertEqual(post.header_image.name, "blog/images/a-review-of-thing.png")

    def test_file_actually_lands_under_media_root(self):
        with override_settings(MEDIA_ROOT=self._tmp):
            post = self.make_post("A Review of Landing")
            path = Path(self._tmp) / post.header_image.name
            self.assertTrue(path.exists(), f"{path} was not written")

    def test_post_without_an_image_is_fine(self):
        post = BlogPost.objects.create(
            title="No Image",
            subtitle="A post with no image",
            author=self.author,
            category=self.cat,
            post_date="2026-07-11",
            content="...",
        )
        self.assertFalse(post.header_image)
