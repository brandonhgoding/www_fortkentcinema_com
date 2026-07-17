from __future__ import annotations

from .models import Film
from .tmdb.services import TMDBService


def import_film_from_tmdb(tmdb_id: int, service: TMDBService | None = None) -> Film:
    """Create a Film from TMDB details, or reuse an existing one matching by
    tmdb_id or imdb_id."""
    existing = Film.objects.filter(tmdb_id=str(tmdb_id)).first()
    if existing is not None:
        return existing

    svc = service or TMDBService()
    details = svc.get_film_details(tmdb_id)

    # A film with this imdb_id may already exist under a different (or absent)
    # tmdb_id — e.g. added manually or by an earlier import. Reuse it rather than
    # creating a duplicate that would violate the imdb_id unique constraint, and
    # backfill the tmdb_id so future lookups take the cheaper tmdb_id path.
    imdb_id = details.get("imdb_id") or ""
    if imdb_id:
        by_imdb = Film.objects.filter(imdb_id=imdb_id).first()
        if by_imdb is not None:
            if not by_imdb.tmdb_id:
                by_imdb.tmdb_id = str(tmdb_id)
                by_imdb.save(update_fields=["tmdb_id"])
            return by_imdb

    return Film.objects.create(
        title=details.get("title", ""),
        tmdb_id=str(details["tmdb_id"]) if details.get("tmdb_id") else None,
        imdb_id=imdb_id,
        poster_url=details.get("poster_path") or "",
        backdrop_url=details.get("backdrop_path") or "",
        overview=details.get("overview") or "",
        runtime_minutes=details.get("runtime"),
    )
