from django.urls import path

from .site_views import PostListView

urlpatterns = [
    path("", PostListView.as_view(), name="blog_list"),
]
