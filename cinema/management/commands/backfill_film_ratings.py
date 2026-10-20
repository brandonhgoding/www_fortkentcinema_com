"""Give TMDB-imported films their MPA rating.

The import only started asking TMDB for the certification in October 2026;
every film imported before that has a blank rating. One-off, safe to rerun:
it touches only films with a TMDB id and no rating.
"""

from cinema.models import Film
from cinema.tmdb import TMDBAPIError, TMDBService
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Fill the blank rating of every TMDB-imported film from TMDB."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change without saving.")

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        service = TMDBService()
        films = Film.objects.filter(rating="").exclude(tmdb_id__isnull=True).exclude(
            tmdb_id="").order_by("title")
        rated = 0
        for film in films:
            try:
                certification = service.get_film_details(int(film.tmdb_id))[
                    "certification"]
            except TMDBAPIError as exc:
                self.stdout.write(f"{film.title}: TMDB error: {exc}")
                continue
            if not certification:
                self.stdout.write(f"{film.title}: no US rating on TMDB")
                continue
            self.stdout.write(f"{film.title}: {certification}")
            rated += 1
            if not dry_run:
                film.rating = certification
                film.save(update_fields=["rating"])
        verb = "Would rate" if dry_run else "Rated"
        self.stdout.write(f"{verb} {rated} film{'' if rated == 1 else 's'}")
