from dataclasses import dataclass, field
from datetime import datetime

import requests
from django.conf import settings


@dataclass
class OMDBResponse:
    title: str = field(metadata={"json_key": "Title"})
    year: str = field(metadata={"json_key": "Year"})
    rated: str = field(metadata={"json_key": "Rated"})
    released: str = field(metadata={"json_key": "Released"})
    runtime: str = field(metadata={"json_key": "Runtime"})
    genre: str = field(metadata={"json_key": "Genre"})
    director: str = field(metadata={"json_key": "Director"})
    writer: str = field(metadata={"json_key": "Writer"})
    actors: str = field(metadata={"json_key": "Actors"})
    plot: str = field(metadata={"json_key": "Plot"})
    poster: str = field(metadata={"json_key": "Poster"})
    ratings: list[dict[str, str]] = field(default_factory=list, metadata={"json_key": "Ratings"})
    meta_score: str = field(default="", metadata={"json_key": "Metascore"})
    imdb_rating: str = field(default="", metadata={"json_key": "imdbRating"})
    imdb_votes: str = field(default="", metadata={"json_key": "imdbVotes"})
    gross: str = field(default="", metadata={"json_key": "BoxOffice"})
    timestamp: datetime = field(default_factory=lambda: datetime.now(), metadata={"json_key": "Timestamp"})

    @classmethod
    def from_json(cls, data: dict) -> "OMDBResponse":
        field_map = {
            f.name: data.get(f.metadata["json_key"], "") for f in cls.__dataclass_fields__.values()
        }
        return cls(**field_map)

    def to_json(self) -> dict:
        return {
            f.metadata["json_key"]: getattr(self, f.name)
            for f in self.__dataclass_fields__.values()
        }


class OpenMovieDatabaseService:
    """
    Service to interact with the Open Movie Database API.
    """

    def __init__(self) -> None:
        api_key = settings.OMDB_API_KEY
        self.base_url = f"http://www.omdbapi.com/?apikey={api_key}&"

    def get_movie_details(self, imdb_id: str) -> OMDBResponse:
        """
        Fetch movie details from the Open Movie Database API using the IMDb ID.
        """
        url = f"{self.base_url}i={imdb_id}&plot=full"
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"Error fetching data from OMDB API: {response.status_code}")
        omdb_response = OMDBResponse.from_json(response.json())
        return omdb_response
