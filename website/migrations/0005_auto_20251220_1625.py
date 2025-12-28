from django.db import migrations
from django.utils.text import slugify
from django.utils import timezone
from datetime import datetime, time

from wagtail.models import Page as WagtailPage
from website.models import BlogPage  # the real Page subclass


def forwards(apps, schema_editor):
    # Historical models
    BlogPost = apps.get_model("blog", "BlogPost")
    Image = apps.get_model("wagtailimages", "Image")

    # Use the *real* Wagtail Page so we have add_child()
    try:
        parent = WagtailPage.objects.get(id=5)
    except WagtailPage.DoesNotExist:
        return

    # Keep track of slugs under this parent
    existing_slugs = set(parent.get_children().values_list("slug", flat=True))

    def make_slug(base: str) -> str:
        base_slug = slugify(base) or "post"
        slug = base_slug
        i = 1
        while slug in existing_slugs:
            slug = f"{base_slug}-{i}"
            i += 1
        existing_slugs.add(slug)
        return slug

    for post in BlogPost.objects.all():
        # Build slug from subtitle (old slug_field) or title
        base_for_slug = post.subtitle or post.title
        slug = make_slug(base_for_slug)

        # Try to re-use or create a wagtail Image for the header
        header_image = None
        if getattr(post, "header_image", None):
            file_name = post.header_image.name
            if file_name:
                existing = Image.objects.filter(file=file_name).first()
                if existing:
                    header_image = existing
                else:
                    img = Image(title=post.title or "Blog header", file=post.header_image)
                    img.save()
                    header_image = img

        # First published time – use post_date if present, else now
        if post.post_date:
            dt = datetime.combine(post.post_date, time.min)
            first_published_at = timezone.make_aware(dt, timezone.get_default_timezone())
        else:
            first_published_at = timezone.now()

        # Use the real BlogPage model so add_child works
        new_page = BlogPage(
            title=post.title,
            subtitle=post.subtitle,
            slug=slug,
            author_id=post.author_id,
            category_id=post.category_id,
            post_date=post.post_date,
            content=post.content,
            header_image=None,
            live=True,
            first_published_at=first_published_at,
        )

        # This sets path/depth/numchild correctly
        parent.add_child(instance=new_page)

        # Ensure a revision exists & is published
        new_page.save_revision().publish()


def backwards(apps, schema_editor):
    # Simple reverse: delete BlogPages under the BlogIndex (id=5)
    try:
        parent = WagtailPage.objects.get(id=5)
    except WagtailPage.DoesNotExist:
        return

    # Use the real BlogPage model
    BlogPage.objects.child_of(parent).delete()


class Migration(migrations.Migration):

    dependencies = [
        # whatever migration created BlogPage
        ("website", "0004_membershippage"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
