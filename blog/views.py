from rest_framework import viewsets

from .models import BlogAuthor, BlogCategory, BlogPost
from .serializers import (
    BlogCategorySerializer,
    BlogPostAuthorSerializer,
    BlogPostSerializer,
)


class BlogPostViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for published blog posts (read-only).

    Posts are written in the dashboard. This used to be a ModelViewSet, which
    let any logged-in account create, edit or delete posts.
    """

    queryset = BlogPost.objects.published()
    serializer_class = BlogPostSerializer
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
