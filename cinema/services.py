from __future__ import annotations

from .models import Film
from .tmdb.services import TMDBService


def import_film_from_tmdb(tmdb_id: int, service: TMDBService | None = None) -> Film:
    """Create a Film from TMDB details, or reuse an existing one with the same tmdb_id."""
    existing = Film.objects.filter(tmdb_id=str(tmdb_id)).first()
    if existing is not None:
        return existing

    svc = service or TMDBService()
    details = svc.get_film_details(tmdb_id)
    return Film.objects.create(
        title=details.get("title", ""),
        tmdb_id=str(details["tmdb_id"]) if details.get("tmdb_id") else None,
        imdb_id=details.get("imdb_id") or "",
        poster_url=details.get("poster_path") or "",
        backdrop_url=details.get("backdrop_path") or "",
        overview=details.get("overview") or "",
        runtime_minutes=details.get("runtime"),
    )
