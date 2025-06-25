import requests
from django.conf import settings


class OpenMovieDatabaseService:
    """
    Service to interact with the Open Movie Database API.
    """

    def __init__(self) -> None:
        api_key = settings.OMDB_API_KEY
        self.base_url = f"http://www.omdbapi.com/?apikey={api_key}&"

    def get_movie_details(self, imdb_id: str) -> dict:
        """
        Fetch movie details from the Open Movie Database API using the IMDb ID.
        """
        url = f"{self.base_url}i={imdb_id}&plot=full"
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"Error fetching data from OMDB API: {response.status_code}")
        return response.json()  # type: ignore[no-any-return]
