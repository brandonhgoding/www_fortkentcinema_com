from collections.abc import Iterable
from datetime import date, datetime

from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from cinema.models import Film
from cinema.serializers import (FilmArchiveSerializer, FilmCalendarSerializer,
                                FilmSerializer)
from cinema.utils import ensure_film_omdb_up_to_date


class FilmArchiveApiView(APIView):
    """
    API view for handling film-related requests.
    """

    permission_classes: list = []
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        films_qs = Film.objects.filter(omdb_json__isnull=False)
        self._parse_released_dates(films_qs)
        films = self._filter_and_sort_films(films_qs)
        paginator = PageNumberPagination()
        paginator.page_size = 6
        result_page = paginator.paginate_queryset(films, request)
        serializer = FilmArchiveSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def _parse_released_dates(self, films: QuerySet) -> None:
        for film in films:
            released_str = film.omdb_json.get("Released", "")
            try:
                film.omdb_json["Released"] = datetime.strptime(released_str, "%d %b %Y").date()
            except ValueError:
                film.omdb_json["Released"] = None

    def _filter_and_sort_films(self, films: Iterable[Film]) -> list[Film]:
        filtered = [
            film
            for film in films
            if isinstance(film.omdb_json, dict)
            and isinstance(film.omdb_json.get("Released"), date)
            and film.omdb_json["Released"] <= datetime.now().date()
        ]
        return sorted(
            filtered,
            key=lambda x: (
                x.omdb_json["Released"]
                if isinstance(x.omdb_json, dict) and isinstance(x.omdb_json.get("Released"), date)
                else datetime.max.date()
            ),
            reverse=True,
        )


class FilmArchiveDetailApiView(APIView):
    """
    API view for retrieving a single film by slug.
    """

    permission_classes: list = []
    authentication_classes: list = []

    def get(self, request: Request, slug: str) -> Response:
        film = get_object_or_404(Film, slug=slug)
        ensure_film_omdb_up_to_date(film)
        serializer = FilmSerializer(film)
        return Response(serializer.data, status=200)


class NowPlayingApiView(APIView):
    """
    API view for retrieving up to two 'now playing' films.
    """

    permission_classes: list = []
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        now = timezone.now()
        films = Film.objects.filter(
            bookings__booking_start_date__lte=now, bookings__booking_end_date__gte=now
        ).order_by("bookings__booking_start_date")[:2]
        serializer = FilmSerializer(films, many=True)
        return Response(serializer.data, status=200)


class ComingSoonApiView(APIView):
    """
    API view for retrieving up to two 'coming soon' films.
    """

    permission_classes: list = []
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        now = timezone.now()
        films = Film.objects.filter(
            bookings__booking_start_date__gt=now, bookings__confirmed=True
        ).order_by("bookings__booking_start_date")[:3]
        serializer = FilmSerializer(films, many=True)
        return Response(serializer.data, status=200)


class ComingSoonCalendarApiView(APIView):
    """
    API view for retrieving 'coming soon' films with a calendar format.
    """

    permission_classes: list = []
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        films = Film.objects.all()
        serializer = FilmCalendarSerializer(films, many=True)
        return Response(serializer.data, status=200)
