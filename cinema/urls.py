from django.urls import path

from . import views as cinema_views

urlpatterns = [
    path("", cinema_views.FilmsApiView.as_view(), name="films-list"),
]
