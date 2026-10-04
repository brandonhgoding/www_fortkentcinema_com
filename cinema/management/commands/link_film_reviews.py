"""Link films to our own blog reviews of them.

A movie page whose only prose is the TMDB overview is a duplicate-content page —
the same blurb sits on TMDB, IMDb and every other cinema site. Our own review is
the one piece of writing about a film that is genuinely ours, so surfacing it on
the movie page (and linking back) is worth real SEO weight.

MATCHING ON THE SLUG, NOT THE TITLE. This is the whole trick, and the first cut
of this command got it wrong and silently matched nothing.

A post's `title` is an editorial headline — "Connecting The Dots", "BACK TO THE
TOY BOX", "Closer Encounters". The film's name lives in the `subtitle`:
`A Review of "Project Hail Mary"`. And those subtitles carry typographic quotes,
inconsistent capitalisation ("A Review of" / "A review of"), and HTML entities.

BlogPost.slug is generated from the subtitle (see BlogPost.slug_field), which
means slugify has already normalised all of that away:

    subtitle: A Review of "Project Hail Mary"
    slug:     a-review-of-project-hail-mary
    film:     Project Hail Mary  ->  project-hail-mary

So comparing slug-to-slug sidesteps quotes, case and entities entirely.

Idempotent: only fills in films whose `review` is unset, so it is safe to re-run
as new reviews are written. Never overwrites a hand-made link.

Only published posts count: a draft 404s publicly, so the film page must not
link to it. When a film has several matching reviews the newest published one
wins, and the film is then done for this run.
"""

import re

from blog.models import BlogPost
from cinema.models import Film
from django.core.management.base import BaseCommand

# Matches the slugified form of "A Review of X", "Review of X", "A Preview of X",
# "An Appreciation of X", "A Review of the Movie X".
SLUG_PREFIX = re.compile(r"^(a-|an-)?(review|preview|appreciation)-of-(the-movie-)?")


def film_slug_for(post_slug: str) -> str:
    """The film slug a post's slug implies, or '' if it isn't review-shaped."""
    if not post_slug:
        return ""
    stripped = SLUG_PREFIX.sub("", post_slug)
    if stripped == post_slug:
        return ""  # no review-ish prefix — don't guess
    return stripped


class Command(BaseCommand):
    help = "Link Film.review to the blog post reviewing that film, matching on slugs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be linked without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        films_by_slug = {
            f.slug: f for f in Film.objects.filter(review__isnull=True) if f.slug
        }
        linked = 0

        for post in BlogPost.objects.published().order_by("-post_date", "-id"):
            slug = film_slug_for(post.slug)
            if not slug:
                continue
            # pop, not get: newest first, so the first match is the one to keep.
            film = films_by_slug.pop(slug, None)
            if not film:
                continue

            self.stdout.write(f"  {film.title}  ->  /blog/{post.slug}")
            if not dry_run:
                film.review = post
                film.save(update_fields=["review"])
            linked += 1

        verb = "would link" if dry_run else "linked"
        self.stdout.write(self.style.SUCCESS(f"{verb} {linked} film(s) to a review."))
        if not linked:
            self.stdout.write(
                "No unlinked films matched a review slug. Link the rest by hand "
                "in the dashboard: open the post under Blog and set Reviews film."
            )
