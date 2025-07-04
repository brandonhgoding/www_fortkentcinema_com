from datetime import timedelta

from dateutil.parser import parse as parse_datetime
from django.utils import timezone

from cinema.models import Film
from cinema.services import OpenMovieDatabaseService


def update_omdb(film: Film) -> None:
    service = OpenMovieDatabaseService()
    response = service.get_movie_details(imdb_id=film.imdb_id)
    if response:
        film.omdb_json = response.to_json()
        film.save()


def ensure_film_omdb_up_to_date(film: Film) -> None:
    if not film.omdb_json:
        update_omdb(film)
    elif timestamp := film.omdb_json.get("timestamp"):
        timestamp_dt = parse_datetime(timestamp)
        one_week_ago = timezone.now() - timedelta(days=7)
        if timestamp_dt < one_week_ago:
            update_omdb(film)
