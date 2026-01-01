from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from .models import BlogAuthor, BlogCategory, BlogPost
from .serializers import (
    BlogCategorySerializer,
    BlogPostAuthorSerializer,
    BlogPostSerializer,
)


class BlogPostViewSet(viewsets.ModelViewSet):
    """
    API endpoint for blog posts.
    - GET (list/retrieve): Public access
    - POST/PUT/PATCH/DELETE: Requires authentication
    """

    queryset = BlogPost.objects.all()
    serializer_class = BlogPostSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = "slug"


class BlogAuthorViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for blog authors (read-only).
    """

    queryset = BlogAuthor.objects.all()
    serializer_class = BlogPostAuthorSerializer
    lookup_field = "slug"


class BlogCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for blog categories (read-only).
    """

    queryset = BlogCategory.objects.all()
    serializer_class = BlogCategorySerializer
    lookup_field = "slug"
