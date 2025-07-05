from django.urls import path

from . import views as cinema_views

film_urlpatterns = [
    path("", cinema_views.FilmArchiveApiView.as_view(), name="films-list"),
    path("now-playing/", cinema_views.NowPlayingApiView.as_view(), name="now-playing"),
    path("coming-soon/", cinema_views.ComingSoonApiView.as_view(), name="coming-soon"),
    path("<slug:slug>/", cinema_views.FilmDetailApiView.as_view(), name="film-detail"),
]
