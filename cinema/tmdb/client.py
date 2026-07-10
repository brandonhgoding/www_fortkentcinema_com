# films/tmdb/client.py
import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class TMDBAPIError(Exception):
    """Exception raised when TMDB API returns an error."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class TMDBClient:
    """
    Wrapper around TMDB API for film data operations.
    Handles authentication, error handling, and common operations.
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize TMDB client with API key.

        Args:
            api_key: TMDB API key (defaults to settings.TMDB_API_KEY)
        """
        self.api_key = api_key or settings.TMDB_API_KEY
        self.base_url = settings.TMDB_BASE_URL
        self.image_base_url = settings.TMDB_IMAGE_BASE_URL

        if not self.api_key:
            raise ValueError("TMDB API key is required")

    def _make_request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Make a request to the TMDB API.

        Args:
            endpoint: API endpoint path (e.g., '/search/movie')
            params: Query parameters

        Returns:
            Response data as dict

        Raises:
            TMDBAPIError: If the API request fails
        """
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params["api_key"] = self.api_key

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
        except requests.exceptions.HTTPError as e:
            error_data = {}
            try:
                error_data = e.response.json()
            except (ValueError, AttributeError):
                # Best-effort: response body may not be JSON or response
                # may be None; the real error is raised below regardless.
                pass

            raise TMDBAPIError(
                message=f"TMDB API error: {e}",
                status_code=e.response.status_code,
                response_data=error_data,
            )
        except requests.exceptions.RequestException as e:
            raise TMDBAPIError(message=f"TMDB API request failed: {e}")
        except ValueError as e:
            raise TMDBAPIError(message=f"Invalid JSON response from TMDB: {e}")

    def search_movies(
        self, query: str, page: int = 1, include_adult: bool = False
    ) -> dict[str, Any]:
        """
        Search for movies by title.

        Args:
            query: Search query string
            page: Page number (default: 1)
            include_adult: Include adult content (default: False)

        Returns:
            Dict with 'results', 'page', 'total_pages', 'total_results'

        Raises:
            TMDBAPIError: If the search fails
        """
        params = {
            "query": query,
            "page": page,
            "include_adult": include_adult,
        }
        return self._make_request("/search/movie", params)

    def get_movie_details(self, movie_id: int) -> dict[str, Any]:
        """
        Get detailed information about a specific movie.

        Args:
            movie_id: TMDB movie ID

        Returns:
            Movie details dict

        Raises:
            TMDBAPIError: If the request fails
        """
        return self._make_request(f"/movie/{movie_id}")

    def build_image_url(self, path: str | None, size: str = "w500") -> str:
        """
        Build a full image URL from a TMDB image path.

        Args:
            path: Image path from TMDB (e.g., '/abc123.jpg')
            size: Image size (w92, w154, w185, w342, w500, w780, original)

        Returns:
            Full image URL, or empty string if path is None
        """
        if not path:
            return ""
        return f"{self.image_base_url}{size}{path}"
