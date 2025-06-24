from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BlogPost
from .serializers import BlogPostSerializer


# Create your views here.
class BlogPostListAPIView(APIView):
    """
    API view to retrieve a list of blog posts.
    """

    authentication_classes: list[str] = []
    permission_classes: list[str] = []

    def get(self, request: Request) -> Response:
        """
        Handle GET requests to retrieve a list of blog posts.
        """
        blog_posts = BlogPost.objects.all()
        serializer = BlogPostSerializer(blog_posts, many=True)
        return Response(serializer.data, status=200)


class BlogPostDetailAPIView(APIView):
    """
    API view to retrieve a single blog post.
    """

    authentication_classes: list[str] = []
    permission_classes: list[str] = []

    def get(self, request: Request, slug: str) -> Response:
        try:
            blog_post = BlogPost.objects.get(slug=slug)
        except BlogPost.DoesNotExist:
            return Response({"detail": "Blog post not found."}, status=status.HTTP_404_NOT_FOUND)

        # Retrieve the previous and next posts
        prev_post = (
            BlogPost.objects.filter(post_date__lt=blog_post.post_date)
            .order_by("-post_date")
            .first()
        )
        next_post = (
            BlogPost.objects.filter(post_date__gt=blog_post.post_date).order_by("post_date").first()
        )

        serializer = BlogPostSerializer(blog_post)
        data = serializer.data
        data["prev_post"] = prev_post.slug if prev_post else None
        data["next_post"] = next_post.slug if next_post else None
        return Response(data, status=200)
