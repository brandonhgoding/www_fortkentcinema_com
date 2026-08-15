from django.urls import path

from .views import (
    # AboutView,  # About page temporarily hidden (re-enable with the /about path below)
    CalendarMonthView,
    HomeView,
    MovieDetailView,
    RentalsView,
    ThanksView,
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("rentals/", RentalsView.as_view(), name="rentals"),
    # path("about/", AboutView.as_view(), name="about"),  # About page temporarily hidden — re-enable this + the AboutView import to restore /about
    # Square redirects here after a successful payment. noindex, unlinked,
    # and deliberately absent from the sitemap.
    path("thanks", ThanksView.as_view(), name="thanks"),
    # No trailing slash, matching /blog/<slug>: detail pages are slugless-suffix,
    # section pages (/rentals/) keep theirs.
    path("movies/<slug:slug>", MovieDetailView.as_view(), name="movie_detail"),
    path(
        "calendar/<int:year>/<int:month>/",
        CalendarMonthView.as_view(),
        name="calendar_month",
    ),
]
