"""Header images are resized and re-encoded on the way in.

The audit measured /blog/ at 10.5 MB: header images went up as 2-3 MB PNGs
straight from an image generator or a phone, 1200-1700px wide, and were shown
in ~350px cards. Large or heavy uploads are now capped at MAX_WIDTH and saved
as WebP; small ones are left exactly as uploaded.
"""

import io
import shutil
import tempfile
from pathlib import Path

from blog.images import MAX_WIDTH, optimise_header_image
from blog.models import BlogAuthor, BlogCategory, BlogPost
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from .test_header_image import PNG


def image_bytes(size=(2000, 250), fmt="PNG", mode="RGB", noise=True, **save):
    """A real image heavy enough to need optimising. Noise, because a flat
    colour compresses to almost nothing in any format."""
    if noise:
        img = Image.frombytes(mode, size, bytes(_noise(size, mode)))
    else:
        img = Image.new(mode, size)
    buf = io.BytesIO()
    img.save(buf, fmt, **save)
    return buf.getvalue()


def _noise(size, mode):
    import random

    rng = random.Random(1)
    return rng.randbytes(size[0] * size[1] * len(mode))


def opened(data):
    return Image.open(io.BytesIO(data))


class OptimiseHeaderImageTests(SimpleTestCase):
    def test_large_png_becomes_capped_webp(self):
        result = optimise_header_image(ContentFile(image_bytes(), name="big.png"))
        self.assertIsNotNone(result)
        self.assertTrue(result.name.endswith(".webp"))
        img = opened(result.read())
        self.assertEqual(img.format, "WEBP")
        self.assertEqual(img.width, MAX_WIDTH)
        self.assertEqual(img.height, round(250 * MAX_WIDTH / 2000))

    def test_small_light_image_is_left_alone(self):
        self.assertIsNone(optimise_header_image(ContentFile(PNG, name="tiny.png")))

    def test_heavy_image_within_width_is_still_recompressed(self):
        data = image_bytes(size=(600, 300))
        self.assertGreater(len(data), 300_000)
        result = optimise_header_image(ContentFile(data, name="phone.png"))
        self.assertIsNotNone(result)
        self.assertEqual(opened(result.read()).width, 600)

    def test_transparency_survives(self):
        data = image_bytes(mode="RGBA")
        result = optimise_header_image(ContentFile(data, name="logo.png"))
        self.assertEqual(opened(result.read()).mode, "RGBA")

    def test_animated_gif_is_left_alone(self):
        frames = [Image.new("RGB", (2000, 1000), c) for c in ("red", "blue")]
        buf = io.BytesIO()
        frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
        self.assertIsNone(
            optimise_header_image(ContentFile(buf.getvalue(), name="a.gif"))
        )

    def test_unreadable_file_is_left_alone(self):
        """Validation is ImageField's job; this must never raise."""
        self.assertIsNone(optimise_header_image(ContentFile(b"nope", name="x.png")))


class MediaTestCase(TestCase):
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
        self.author = BlogAuthor.objects.create(first_name="Rick", last_name="Douglas")
        self.cat = BlogCategory.objects.create(name="Reviews")

    def make_post(self, **extra):
        return BlogPost.objects.create(
            title="Gods and Monsters",
            subtitle="A Review of The Odyssey",
            author=self.author,
            category=self.cat,
            post_date="2026-07-20",
            content="...",
            **extra,
        )


class UploadOptimisationTests(MediaTestCase):
    def test_heavy_upload_is_stored_as_webp(self):
        post = self.make_post(
            header_image=SimpleUploadedFile("ODYSSEY.png", image_bytes())
        )
        post.refresh_from_db()
        self.assertRegex(
            post.header_image.name,
            r"^blog/images/a-review-of-the-odyssey-[0-9a-f]{8}\.webp$",
        )
        with post.header_image.open("rb") as f:
            self.assertEqual(opened(f.read()).width, MAX_WIDTH)

    def test_replacing_with_a_heavy_upload_still_deletes_the_old_file(self):
        post = self.make_post(header_image=SimpleUploadedFile("a.png", PNG))
        old = Path(self._tmp) / post.header_image.name
        with self.captureOnCommitCallbacks(execute=True):
            post.header_image = SimpleUploadedFile("b.png", image_bytes())
            post.save()
        self.assertFalse(old.exists())
        self.assertTrue(post.header_image.name.endswith(".webp"))


class OptimiseCommandTests(MediaTestCase):
    def legacy_post(self, name, data):
        path = Path(self._tmp) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        post = self.make_post()
        # Straight to the column, as the legacy rows were: no upload, no hook.
        BlogPost.objects.filter(pk=post.pk).update(header_image=name)
        return BlogPost.objects.get(pk=post.pk), path

    def run_command(self, *args):
        out = io.StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("optimise_blog_images", *args, stdout=out)
        return out.getvalue()

    def test_converts_a_heavy_legacy_image_and_removes_the_original(self):
        post, path = self.legacy_post("blog/images/ChatGPT_Image.png", image_bytes())
        out = self.run_command()
        post.refresh_from_db()
        self.assertTrue(post.header_image.name.endswith(".webp"))
        self.assertTrue((Path(self._tmp) / post.header_image.name).exists())
        self.assertFalse(path.exists())
        self.assertIn("ChatGPT_Image.png", out)

    def test_dry_run_changes_nothing(self):
        post, path = self.legacy_post("blog/images/big.png", image_bytes())
        out = self.run_command("--dry-run")
        post.refresh_from_db()
        self.assertEqual(post.header_image.name, "blog/images/big.png")
        self.assertTrue(path.exists())
        self.assertIn("big.png", out)

    def test_light_image_is_left_alone(self):
        post, path = self.legacy_post("blog/images/small.png", PNG)
        self.run_command()
        post.refresh_from_db()
        self.assertEqual(post.header_image.name, "blog/images/small.png")

    def test_missing_files_are_reported_not_cleared_by_default(self):
        post = self.make_post()
        BlogPost.objects.filter(pk=post.pk).update(header_image="blog/images/GONE.jpg")
        out = self.run_command()
        self.assertIn("GONE.jpg", out)
        post.refresh_from_db()
        self.assertEqual(post.header_image.name, "blog/images/GONE.jpg")

    def test_clear_missing_blanks_the_field(self):
        post = self.make_post()
        BlogPost.objects.filter(pk=post.pk).update(header_image="blog/images/GONE.jpg")
        self.run_command("--clear-missing")
        post.refresh_from_db()
        self.assertFalse(post.header_image)
