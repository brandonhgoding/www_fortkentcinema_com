"""Link films to our own blog reviews of them.

A movie page whose only prose is the TMDB overview is a duplicate-content page —
the same blurb sits on TMDB, IMDb and every other cinema site. Our own review is
the one piece of writing about a film that is genuinely ours, so surfacing it on
the movie page (and linking back) is worth real SEO weight.

Most reviews are titled "A Review of <Film>", so the obvious matches can be made
automatically. The rest are linked by hand in Django admin (FilmAdmin.review).

Idempotent: only fills in films whose `review` is unset, so it is safe to re-run
as new reviews are written. Never overwrites a hand-made link.
"""

import re

from blog.models import BlogPost
from cinema.models import Film
from django.core.management.base import BaseCommand
from django.utils.text import slugify

# "A Review of X", "Review of X", "A Preview of X", "An Appreciation of X",
# "A Review of the Movie X"
TITLE_PREFIX = re.compile(
    r"^(a|an)?[\s-]*(review|preview|appreciation)[\s-]+of[\s-]+(the[\s-]+movie[\s-]+)?",
    re.IGNORECASE,
)


def film_slug_for(post_title: str) -> str:
    """The film slug a post title implies, or '' if it isn't review-shaped."""
    stripped = TITLE_PREFIX.sub("", post_title.strip())
    if stripped == post_title.strip():
        return ""  # no review-ish prefix — don't guess
    return slugify(stripped)


class Command(BaseCommand):
    help = "Link Film.review to the blog post reviewing that film, where the title matches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be linked without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        films_by_slug = {f.slug: f for f in Film.objects.filter(review__isnull=True) if f.slug}
        linked = 0

        for post in BlogPost.objects.all():
            slug = film_slug_for(post.title)
            if not slug:
                continue
            film = films_by_slug.get(slug)
            if not film:
                continue

            self.stdout.write(f"  {film.title}  ->  /blog/{post.slug}")
            if not dry_run:
                film.review = post
                film.save(update_fields=["review"])
            linked += 1

        verb = "would link" if dry_run else "linked"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} {linked} film(s) to a review.")
        )
        if not linked:
            self.stdout.write(
                "No unlinked films matched a review title. "
                "Link the rest by hand in admin (Film > review)."
            )
