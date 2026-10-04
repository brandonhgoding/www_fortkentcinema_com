from django.urls import path
from django.views.generic import RedirectView

from .site_views import PostDetailView, PostListView

urlpatterns = [
    path("", PostListView.as_view(), name="blog_list"),
    path("<slug:slug>", PostDetailView.as_view(), name="blog_detail"),
    # The canonical URL has no trailing slash, but links get written with one.
    path(
        "<slug:slug>/",
        RedirectView.as_view(pattern_name="blog_detail", permanent=True),
    ),
]
