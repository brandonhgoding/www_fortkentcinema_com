from django.utils import timezone
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from cinema.models import Film
from cinema.serializers import FilmSerializer


class FilmsApiView(APIView):
    """
    API view for handling film-related requests.
    """

    permission_classes: list = []
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        blog_posts = Film.objects.all()
        serializer = FilmSerializer(blog_posts, many=True)
        return Response(serializer.data, status=200)


class FilmDetailApiView(APIView):
    """
    API view for retrieving a single film by slug.
    """

    permission_classes: list = []
    authentication_classes: list = []

    def get(self, request: Request, slug: str) -> Response:
        film = get_object_or_404(Film, slug=slug)
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
        films = Film.objects.filter(bookings__booking_start_date__gt=now).order_by(
            "bookings__booking_start_date"
        )[:3]
        serializer = FilmSerializer(films, many=True)
        return Response(serializer.data, status=200)
