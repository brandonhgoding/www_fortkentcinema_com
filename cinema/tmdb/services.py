# films/tmdb/services.py
import hashlib
import logging
from typing import Any

from django.core.cache import cache

from .client import TMDBClient

logger = logging.getLogger(__name__)


class TMDBService:
    """
    Service layer for TMDB film data operations.
    Provides normalized data structures for consumption by the application.
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize TMDB service.

        Args:
            api_key: TMDB API key (defaults to settings.TMDB_API_KEY)
        """
        self.client = TMDBClient(api_key=api_key)

    def search_films(self, query: str, page: int = 1) -> list[dict[str, Any]]:
        """
        Search for films by title and return normalized results.

        Args:
            query: Search query string
            page: Page number (default: 1)

        Returns:
            List of normalized film data dicts with keys:
                - tmdb_id: int
                - title: str
                - release_date: str (YYYY-MM-DD or empty)
                - overview: str
                - poster_path: str (full URL or empty)
                - backdrop_path: str (full URL or empty)
                - runtime: int | None (not available in search, set to None)
                - genres: list[str] (not available in search, empty list)
                - vote_average: float
                - popularity: float

        Raises:
            TMDBAPIError: If the search fails
        """
        cache_key = (
            f"tmdb_search:{hashlib.sha256(f'{query}:{page}'.encode()).hexdigest()}"
        )
        cached: list[dict[str, Any]] | None = cache.get(cache_key)
        if cached is not None:
            return cached

        response = self.client.search_movies(query, page=page, include_adult=False)
        results = response.get("results", [])

        normalized_films = []
        for movie in results:
            normalized = self._normalize_search_result(movie)
            normalized_films.append(normalized)

        cache.set(cache_key, normalized_films, timeout=300)  # 5 minutes
        return normalized_films

    def get_film_details(self, tmdb_id: int) -> dict[str, Any]:
        """
        Get detailed information about a specific film.

        Args:
            tmdb_id: TMDB movie ID

        Returns:
            Normalized film data dict with keys:
                - tmdb_id: int
                - title: str
                - release_date: str (YYYY-MM-DD or empty)
                - overview: str
                - poster_path: str (full URL or empty)
                - backdrop_path: str (full URL or empty)
                - runtime: int | None (minutes)
                - genres: list[str] (genre names)
                - vote_average: float
                - popularity: float
                - imdb_id: str | None
                - certification: str (the US MPA rating, or "")

        Raises:
            TMDBAPIError: If the request fails
        """
        movie = self.client.get_movie_details(tmdb_id)
        return self._normalize_film_details(movie)

    def _normalize_search_result(self, movie: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize a movie search result to our standard format.

        Args:
            movie: Raw movie data from TMDB search

        Returns:
            Normalized film data dict
        """
        return {
            "tmdb_id": movie.get("id"),
            "title": movie.get("title", ""),
            "release_date": movie.get("release_date", ""),
            "overview": movie.get("overview", ""),
            "poster_path": self.client.build_image_url(
                movie.get("poster_path"), size="w500"
            ),
            "backdrop_path": self.client.build_image_url(
                movie.get("backdrop_path"), size="w780"
            ),
            "runtime": None,  # Not available in search results
            "genres": [],  # Not available in search results
            "vote_average": movie.get("vote_average", 0.0),
            "popularity": movie.get("popularity", 0.0),
        }

    def _normalize_film_details(self, movie: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize detailed movie data to our standard format.

        Args:
            movie: Raw movie data from TMDB details endpoint

        Returns:
            Normalized film data dict
        """
        # Extract genre names
        genres = [g.get("name", "") for g in movie.get("genres", [])]

        return {
            "tmdb_id": movie.get("id"),
            "title": movie.get("title", ""),
            "release_date": movie.get("release_date", ""),
            "overview": movie.get("overview", ""),
            "poster_path": self.client.build_image_url(
                movie.get("poster_path"), size="w500"
            ),
            "backdrop_path": self.client.build_image_url(
                movie.get("backdrop_path"), size="w780"
            ),
            "runtime": movie.get("runtime"),
            "genres": genres,
            "vote_average": movie.get("vote_average", 0.0),
            "popularity": movie.get("popularity", 0.0),
            "imdb_id": movie.get("imdb_id"),
            "certification": us_certification(movie),
        }


# TMDB release types: 3 is the theatrical release, the one the MPA rated.
THEATRICAL = 3


def us_certification(movie: dict[str, Any]) -> str:
    """The US rating from an appended ``release_dates`` block, or "".

    A film is listed once per release (theatrical, digital, physical, TV)
    and a re-rated classic can disagree across them, so the theatrical
    rating wins; any other non-blank US rating is the fallback.
    """
    for country in movie.get("release_dates", {}).get("results", []):
        if country.get("iso_3166_1") != "US":
            continue
        releases = country.get("release_dates", [])
        rated = [r for r in releases if (r.get("certification") or "").strip()]
        theatrical = [r for r in rated if r.get("type") == THEATRICAL]
        for release in theatrical + rated:
            return release["certification"].strip()
    return ""
