"""Shrink header images that went up before uploads were optimised.

    python manage.py optimise_blog_images --dry-run
    python manage.py optimise_blog_images
    python manage.py optimise_blog_images --clear-missing

Each heavy image is re-saved as WebP under a fresh name (the same path a new
upload takes, so nginx's 30-day cache never serves the old bytes) and the
original is deleted once the row is saved. Rows pointing at a file that is no
longer in storage are listed; --clear-missing blanks them, so their cards
show the placeholder instead of a broken image.
"""

from blog.images import optimise_header_image
from blog.models import BlogPost
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Resize and re-encode heavy blog header images as WebP."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )
        parser.add_argument(
            "--clear-missing",
            action="store_true",
            help="Blank header_image on posts whose file is missing.",
        )

    def handle(self, *args, dry_run=False, clear_missing=False, **options):
        saved = 0
        for post in BlogPost.objects.exclude(header_image="").exclude(
            header_image__isnull=True
        ):
            name = post.header_image.name
            storage = post.header_image.storage

            if not storage.exists(name):
                if clear_missing and not dry_run:
                    post.header_image = None
                    post.save(update_fields=["header_image"])
                    self.stdout.write(f"missing, cleared: {name} ({post.slug})")
                else:
                    self.stdout.write(f"missing: {name} ({post.slug})")
                continue

            with storage.open(name, "rb") as f:
                before = storage.size(name)
                optimised = optimise_header_image(f)
            if optimised is None:
                continue

            after = optimised.size
            saved += before - after
            label = f"{name}: {before // 1024} KB -> {after // 1024} KB"
            if dry_run:
                self.stdout.write(f"would optimise {label}")
                continue

            # One transaction per post, so the original is deleted (on
            # commit, by BlogPost.save) as soon as its row points elsewhere.
            with transaction.atomic():
                post.header_image.save(optimised.name, optimised, save=False)
                post.save(update_fields=["header_image"])
            self.stdout.write(f"optimised {label} -> {post.header_image.name}")

        verb = "would save" if dry_run else "saved"
        self.stdout.write(f"{verb} {saved // 1024} KB in total")
