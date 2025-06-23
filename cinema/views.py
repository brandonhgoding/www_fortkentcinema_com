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
