from django.urls import path

from . import views as cinema_views

film_urlpatterns = [
    path("archive/", cinema_views.FilmArchiveApiView.as_view(), name="films-list"),
    path("now-playing/", cinema_views.NowPlayingApiView.as_view(), name="now-playing"),
    path("coming-soon/", cinema_views.ComingSoonApiView.as_view(), name="coming-soon"),
    path(
        "coming-soon/calendar/",
        cinema_views.ComingSoonCalendarApiView.as_view(),
        name="coming-soon-calendar",
    ),
    path(
        "archive/<slug:slug>/", cinema_views.FilmArchiveDetailApiView.as_view(), name="film-detail"
    ),
]
