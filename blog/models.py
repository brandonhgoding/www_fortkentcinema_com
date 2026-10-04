import secrets
import uuid
from functools import partial
from pathlib import Path

from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify

from . import rendering
from .mixins import SlugModelMixin

HEADER_IMAGE_DIR = "blog/images/"


def blog_header_image_path(instance, filename):
    """Name the upload after the post's slug, plus a short random suffix:
    `blog/images/a-review-of-dune-3f9a1c2e.png`.

    Uploads used to keep whatever the file was called on the author's desktop —
    `ChatGPT_Image_Jul_11_2026_at_05_21_01_PM.png`. Then they were named for the
    slug alone, and each re-upload overwrote the last. That had three problems,
    which the suffix fixes:

    - nginx serves /media/ with a 30-day expiry, so a replaced image kept its
      URL and browsers showed the old one for up to a month.
    - A slug can change and be taken by another post, whose upload then
      replaced a file the first post still pointed at.
    - 'blog/images/' + a 100-character slug overflowed the 100-character
      column. The slug is trimmed so the whole name fits.

    BlogPost.save() deletes the file an upload replaces.

    SlugModelMixin.save() sets `slug` before calling super().save(), and the file
    is written during that super().save(), so the slug is already available here
    even for a brand-new post. The slugify fallback covers a caller that bypasses
    the mixin.
    """
    ext = Path(filename).suffix.lower()[:10]
    suffix = secrets.token_hex(4)
    max_length = instance._meta.get_field("header_image").max_length
    room = max_length - len(HEADER_IMAGE_DIR) - len(f"-{suffix}{ext}")
    slug = instance.slug or slugify(getattr(instance, instance.slug_field, "")) or "post"
    slug = slug[:room].strip("-") or "post"
    return f"{HEADER_IMAGE_DIR}{slug}-{suffix}{ext}"


class BlogAuthor(SlugModelMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    slug_field = "full_name"
    slug_fallback = "author"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class BlogCategory(SlugModelMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)

    slug_field = "name"
    slug_fallback = "category"

    class Meta:
        verbose_name_plural = "Blog categories"

    def __str__(self) -> str:
        return self.name


class BlogPostQuerySet(models.QuerySet):
    def published(self):
        """What the public site may show. Every public read goes through this —
        the default manager still returns drafts, because the dashboard and
        Film.review need to see them."""
        return self.filter(status=BlogPost.Status.PUBLISHED)


class BlogPost(SlugModelMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class BodyFormat(models.TextChoices):
        PLAIN = rendering.PLAIN, "Plain text"
        MARKDOWN = rendering.MARKDOWN, "Markdown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200)
    # PROTECT, not CASCADE: deleting an author or category used to take every
    # post filed under it along with it.
    author = models.ForeignKey(BlogAuthor, on_delete=models.PROTECT)
    category = models.ForeignKey(BlogCategory, on_delete=models.PROTECT)
    post_date = models.DateField()
    # Rendered by blog.rendering.render_body, in body_format.
    content = models.TextField()
    # Posts from before the dashboard editor are plain text, and render
    # exactly as they always did. Everything written since is Markdown.
    body_format = models.CharField(
        max_length=10, choices=BodyFormat.choices, default=BodyFormat.MARKDOWN
    )
    summary = models.TextField(blank=True, null=True)
    header_image = models.ImageField(
        upload_to=blog_header_image_path,
        null=True,
        blank=True,
    )
    # Defaults to published so rows made outside the dashboard (tests, the
    # shell) behave as every post did before drafts existed. The dashboard
    # editor starts each new post as a draft.
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PUBLISHED
    )
    # When the row was made: for a dashboard post, the day its draft was
    # started. Null for posts from before this field existed.
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    objects = BlogPostQuerySet.as_manager()

    slug_field = "subtitle"
    slug_fallback = "post"

    class Meta:
        ordering = ["-post_date"]

    def __str__(self) -> str:
        return self.subtitle

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        # The stored name, read before anything can replace it, so save() can
        # tell when an upload replaced the file. Read from __dict__ so a
        # deferred header_image isn't fetched just for this.
        instance._stored_header_image = instance.__dict__.get("header_image") or ""
        return instance

    def refresh_from_db(self, using=None, fields=None, from_queryset=None):
        super().refresh_from_db(using=using, fields=fields, from_queryset=from_queryset)
        if (fields is None or "header_image" in fields) and "header_image" in self.__dict__:
            self._stored_header_image = self.header_image.name or ""

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)
        if "header_image" not in self.__dict__:
            return  # deferred and untouched
        before = getattr(self, "_stored_header_image", "")
        after = self.header_image.name or ""
        self._stored_header_image = after
        if before and before != after:
            # After commit: if the save is rolled back, the row still points
            # at the old file.
            transaction.on_commit(partial(_delete_header_image, self.header_image.storage, before))

    def date_for_publishing(self) -> None:
        """Move post_date to today when a draft goes live, if it is still the
        day the draft was started.

        The editor pre-fills today on a new post, so an untouched date is the
        draft-start day, and a post drafted on the 1st and published on the
        20th would go out dated the 1st. Any other date was set on purpose (a
        backdated review, say) and stays. A post from before created_at
        existed can't be told apart, so it keeps its date too.
        """
        if self.created_at and self.post_date == timezone.localdate(self.created_at):
            self.post_date = timezone.localdate()

    @property
    def is_plain(self) -> bool:
        return self.body_format == self.BodyFormat.PLAIN

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("blog_detail", kwargs={"slug": self.slug})


def _delete_header_image(storage, name: str) -> None:
    """Remove a header image an upload (or Remove image) replaced, unless some
    other post still points at it."""
    if not BlogPost.objects.filter(header_image=name).exists():
        storage.delete(name)
