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
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

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


# blog/images/<slug>-<8 hex>.<ext>
VERSIONED = r"blog/images/{slug}-[0-9a-f]{{8}}\.{ext}"


class HeaderImageNamingTests(TestCase):
    """Uploads are named for the post's slug, not whatever the file was called
    on the author's desktop (`ChatGPT_Image_Jul_11_2026_at_05_21_01_PM.png`).

    Each upload also gets a short random suffix. nginx serves /media/ with a
    30-day expiry, so a re-upload under the same name was served stale; and a
    name derived from the slug alone let one post's upload replace another
    post's file.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.mkdtemp()
        cls._media = override_settings(MEDIA_ROOT=cls._tmp)
        cls._media.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media.disable()
        shutil.rmtree(cls._tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.author = BlogAuthor.objects.create(first_name="Brandon", last_name="Goding")
        self.cat = BlogCategory.objects.create(name="Reviews")

    def make_post(self, subtitle, filename="ChatGPT_Image_Jul_11_2026.png", content=PNG, **extra):
        return BlogPost.objects.create(
            title="Connecting The Dots",
            subtitle=subtitle,
            author=self.author,
            category=self.cat,
            post_date="2026-07-11",
            content="...",
            header_image=SimpleUploadedFile(filename, content, content_type="image/png"),
            **extra,
        )

    def upload(self, post, content=PNG, filename="other.png"):
        with self.captureOnCommitCallbacks(execute=True):
            post.header_image = SimpleUploadedFile(filename, content, content_type="image/png")
            post.save()
        post.refresh_from_db()
        return post

    def test_upload_is_named_for_the_post_slug(self):
        post = self.make_post('A Review of "Project Hail Mary"')
        self.assertEqual(post.slug, "a-review-of-project-hail-mary")
        self.assertRegex(
            post.header_image.name,
            VERSIONED.format(slug="a-review-of-project-hail-mary", ext="png"),
        )

    def test_extension_is_preserved_and_lowercased(self):
        post = self.make_post("A Review of Thing", filename="PHOTO.JPEG", content=PNG)
        self.assertTrue(post.header_image.name.endswith(".jpeg"))

    def test_reupload_gets_a_fresh_name_and_removes_the_old_file(self):
        """A fresh URL per upload, so the 30-day cache can't serve the old
        image, and the replaced file doesn't linger."""
        post = self.make_post("A Review of Thing")
        first = post.header_image.name
        post = self.upload(post)

        self.assertNotEqual(post.header_image.name, first)
        self.assertRegex(post.header_image.name, VERSIONED.format(slug="a-review-of-thing", ext="png"))
        self.assertTrue((Path(self._tmp) / post.header_image.name).exists())
        self.assertFalse((Path(self._tmp) / first).exists())

    def test_removing_the_image_deletes_the_file(self):
        post = self.make_post("A Review of Removal")
        old = Path(self._tmp) / post.header_image.name
        with self.captureOnCommitCallbacks(execute=True):
            post.header_image = None
            post.save()
        self.assertFalse(old.exists())

    def test_unrelated_save_keeps_the_file(self):
        post = self.make_post("A Review of Keeping")
        path = Path(self._tmp) / post.header_image.name
        with self.captureOnCommitCallbacks(execute=True):
            post.title = "Retitled"
            post.save()
        fresh = BlogPost.objects.get(pk=post.pk)
        with self.captureOnCommitCallbacks(execute=True):
            fresh.status = BlogPost.Status.DRAFT
            fresh.save(update_fields=["status"])
        self.assertTrue(path.exists())

    def test_one_post_cannot_overwrite_another_posts_file(self):
        """The file was named after the slug and OverwriteStorage deleted
        whatever was already there. Rename post A's URL, give post B A's old
        URL, and B's upload replaced the file A still pointed at."""
        a = self.make_post("A Review of Thing", content=PNG + b"A")
        a_name = a.header_image.name
        a.slug = "a-review-of-thing-renamed"
        a.save()

        self.make_post("A Review of Thing", content=PNG + b"B")

        a.refresh_from_db()
        self.assertEqual(a.header_image.name, a_name)
        self.assertEqual((Path(self._tmp) / a_name).read_bytes(), PNG + b"A")

    def test_long_slug_still_fits_the_column(self):
        """'blog/images/' + a 100-character slug + '.png' is 116 characters,
        past the 100-character column: a DataError on Postgres, and the file
        already written to disk."""
        post = self.make_post("word " * 39)
        self.assertEqual(len(post.slug), 99)
        max_length = BlogPost._meta.get_field("header_image").max_length
        self.assertLessEqual(len(post.header_image.name), max_length)
        self.assertRegex(post.header_image.name, r"^blog/images/word-word-.*-[0-9a-f]{8}\.png$")
        post.refresh_from_db()
        self.assertTrue((Path(self._tmp) / post.header_image.name).exists())

    def test_legacy_paths_still_resolve(self):
        """Names already in the database (from before the suffix) keep working."""
        post = self.make_post("A Review of Old Times")
        legacy = "blog/images/a-review-of-old-times.png"
        (Path(self._tmp) / legacy).write_bytes(PNG)
        BlogPost.objects.filter(pk=post.pk).update(header_image=legacy)
        post.refresh_from_db()
        self.assertEqual(post.header_image.url, "/media/" + legacy)
        self.assertTrue(post.header_image.storage.exists(legacy))

    def test_file_actually_lands_under_media_root(self):
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


class EditorHeaderImageTests(TestCase):
    """The editor must show a replaced image straight away. Under one fixed
    name the browser kept showing its cached copy."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.mkdtemp()
        cls._media = override_settings(MEDIA_ROOT=cls._tmp)
        cls._media.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media.disable()
        shutil.rmtree(cls._tmp, ignore_errors=True)
        super().tearDownClass()

    def test_replacing_the_image_changes_its_url_in_the_editor(self):
        get_user_model().objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="Reviews")
        data = {
            "title": "Opening Night", "subtitle": "We are back", "slug": "",
            "author": str(author.pk), "category": str(cat.pk),
            "post_date": "2026-10-01", "content": "Doors at six.", "status": "draft",
        }

        def upload(url, content):
            image = SimpleUploadedFile("photo.png", content, content_type="image/png")
            with self.captureOnCommitCallbacks(execute=True):
                return self.client.post(url, {**data, "header_image": image}, follow=True)

        upload(reverse("dashboard:blog_post_create"), PNG)
        post = BlogPost.objects.get()
        first_url = post.header_image.url

        resp = upload(reverse("dashboard:blog_post_edit", args=[post.pk]), PNG + b"2")
        post.refresh_from_db()
        html = resp.content.decode()
        self.assertNotEqual(post.header_image.url, first_url)
        self.assertIn(f'src="{post.header_image.url}"', html)
        self.assertNotIn(first_url, html)
        self.assertFalse((Path(self._tmp) / first_url.removeprefix("/media/")).exists())
