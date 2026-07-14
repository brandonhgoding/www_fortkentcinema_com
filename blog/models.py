import uuid
from pathlib import Path

from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.text import slugify

from .mixins import SlugModelMixin


class OverwriteStorage(FileSystemStorage):
    """Replace an existing file instead of suffixing a new name onto it.

    Django's default would turn a re-upload for the same post into
    `a-review-of-thing_Ab3xY.png`, which defeats the point of naming the file
    after the slug in the first place.
    """

    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            self.delete(name)
        return name


def blog_header_image_path(instance, filename):
    """Name the upload after the post's slug.

    Uploads used to keep whatever the file was called on the author's desktop —
    `ChatGPT_Image_Jul_11_2026_at_05_21_01_PM.png` — plus a random suffix from
    Django's collision handling.

    SlugModelMixin.save() sets `slug` before calling super().save(), and the file
    is written during that super().save(), so the slug is already available here
    even for a brand-new post. The slugify fallback covers a caller that bypasses
    the mixin.
    """
    ext = Path(filename).suffix.lower()
    slug = instance.slug or slugify(getattr(instance, instance.slug_field, "")) or "post"
    return f"blog/images/{slug}{ext}"


class BlogAuthor(SlugModelMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    slug_field = "full_name"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class BlogCategory(SlugModelMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)

    slug_field = "name"

    class Meta:
        verbose_name_plural = "Blog categories"

    def __str__(self) -> str:
        return self.name


class BlogPost(SlugModelMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200)
    author = models.ForeignKey(BlogAuthor, on_delete=models.CASCADE)
    category = models.ForeignKey(BlogCategory, on_delete=models.CASCADE)
    post_date = models.DateField()
    content = models.TextField()
    summary = models.TextField(blank=True, null=True)
    header_image = models.ImageField(
        upload_to=blog_header_image_path,
        storage=OverwriteStorage(),
        null=True,
        blank=True,
    )

    slug_field = "subtitle"

    class Meta:
        ordering = ["-post_date"]

    def __str__(self) -> str:
        return self.subtitle

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("blog_detail", kwargs={"slug": self.slug})
