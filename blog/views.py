from rest_framework import viewsets
from rest_framework.pagination import LimitOffsetPagination

from .models import BlogAuthor, BlogCategory, BlogPost
from .serializers import (
    BlogCategorySerializer,
    BlogPostAuthorSerializer,
    BlogPostSerializer,
)


class BlogPostPagination(LimitOffsetPagination):
    # Without a cap, ?limit=100000 serialises every post in one response.
    max_limit = 50


class BlogPostViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for published blog posts (read-only).

    Posts are written in the dashboard. This used to be a ModelViewSet, which
    let any logged-in account create, edit or delete posts.
    """

    # -id breaks ties between posts on the same day. Without it the database
    # may order them differently for each page's LIMIT/OFFSET query.
    queryset = (
        BlogPost.objects.published()
        .select_related("author", "category")
        .order_by("-post_date", "-id")
    )
    serializer_class = BlogPostSerializer
    pagination_class = BlogPostPagination
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
