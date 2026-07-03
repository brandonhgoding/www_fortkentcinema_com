from django.urls import path

from .site_views import PostDetailView, PostListView

urlpatterns = [
    path("", PostListView.as_view(), name="blog_list"),
    path("<slug:slug>", PostDetailView.as_view(), name="blog_detail"),
]
