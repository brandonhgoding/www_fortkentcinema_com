import secrets
import uuid
from functools import partial
from pathlib import Path

from django.db import models, transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver
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

    BlogPost.save() deletes the file an upload replaces, and deleting a post
    deletes its file (_delete_header_image_with_post).

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


# The fields lead_text is worked out from.
LEAD_TEXT_SOURCES = frozenset({"content", "body_format"})


class BlogPostQuerySet(models.QuerySet):
    """lead_text is set in BlogPost.save(). update(), bulk_update() and
    bulk_create() never call save(), so they keep it current here instead.
    Raw SQL, migrations (historical models don't use this queryset) and
    writes through _base_manager are not covered.
    """

    def published(self):
        """What the public site may show. Every public read goes through this —
        the default manager still returns drafts, because the dashboard and
        Film.review need to see them."""
        return self.filter(status=BlogPost.Status.PUBLISHED)

    def update(self, **kwargs):
        # An explicit lead_text wins. bulk_update() below relies on that: it
        # computes lead_text itself and then calls update() with it.
        if not LEAD_TEXT_SOURCES & kwargs.keys() or "lead_text" in kwargs:
            return super().update(**kwargs)
        with transaction.atomic(using=self.db, savepoint=False):
            # Picked before the update, which may change what the filter
            # matches (filter(content=old).update(content=new)).
            pks = list(self.values_list("pk", flat=True))
            rows = super().update(**kwargs)
            # Read back rather than computed from kwargs: the new value may be
            # an expression, and body_format alone needs each row's content.
            base = self.model._base_manager.using(self.db)
            posts = base.filter(pk__in=pks).only("pk", "content", "body_format", "lead_text")
            stale = [post for post in posts if _set_lead_text(post)]
            base.bulk_update(stale, ["lead_text"])
        return rows

    def bulk_update(self, objs, fields, batch_size=None):
        if LEAD_TEXT_SOURCES & set(fields):
            objs = list(objs)
            for obj in objs:
                _set_lead_text(obj)
            fields = [*fields, "lead_text"]
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            _set_lead_text(obj)
        update_fields = kwargs.get("update_fields")
        if update_fields and LEAD_TEXT_SOURCES & set(update_fields):
            kwargs["update_fields"] = [*update_fields, "lead_text"]
        return super().bulk_create(objs, *args, **kwargs)


def _set_lead_text(post: "BlogPost") -> bool:
    """Set post.lead_text from its body; True if that changed it. Read from
    __dict__ so a deferred lead_text isn't fetched just to be overwritten."""
    lead_text = rendering.first_paragraph(post.content, post.body_format)
    changed = lead_text != post.__dict__.get("lead_text")
    post.lead_text = lead_text
    return changed


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
    # The body's first paragraph as plain text, untruncated: what cards and
    # meta descriptions are cut from. Set in save(), so a listing doesn't
    # render every post's Markdown on every request to get it.
    lead_text = models.TextField(blank=True, default="", editable=False)
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
        _set_lead_text(self)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and {"content", "body_format"} & set(update_fields):
            kwargs["update_fields"] = {*update_fields, "lead_text"}
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
    """Remove a header image an upload (or Remove image) replaced, or whose
    post was deleted, unless some other post still points at it."""
    if not BlogPost.objects.filter(header_image=name).exists():
        storage.delete(name)


@receiver(pre_delete, sender=BlogPost, dispatch_uid="blog_delete_header_image_with_post")
def _delete_header_image_with_post(sender, instance: BlogPost, using, **kwargs) -> None:
    """Delete a post's header image along with the post.

    A signal rather than BlogPost.delete(), so a queryset delete (which
    never calls delete() on each row) removes the files too. pre_delete,
    not post_delete: the row still exists, so a deferred header_image can
    still be read. The file goes once the delete commits, and only if no
    other post points at it (checked then, not now); a rolled-back delete
    drops the callback with the transaction.

    The stored name, not whatever is on the instance: an upload assigned but
    never saved isn't in storage under that name.
    """
    if "header_image" in instance.__dict__ and hasattr(instance, "_stored_header_image"):
        name = instance._stored_header_image
    else:
        name = instance.header_image.name  # deferred: loads the stored name
    if name:
        transaction.on_commit(
            partial(_delete_header_image, instance.header_image.storage, name), using=using
        )
