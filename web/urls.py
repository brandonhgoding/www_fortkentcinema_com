from django.urls import path

from .views import (
    # AboutView,  # About page temporarily hidden (re-enable with the /about path below)
    CalendarMonthView,
    ClassicsView,
    HomeView,
    MembershipView,
    RentalsView,
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("membership/", MembershipView.as_view(), name="membership"),
    path("rentals/", RentalsView.as_view(), name="rentals"),
    # path("about/", AboutView.as_view(), name="about"),  # About page temporarily hidden — re-enable this + the AboutView import to restore /about
    path("classics/", ClassicsView.as_view(), name="classics"),
    path(
        "calendar/<int:year>/<int:month>/",
        CalendarMonthView.as_view(),
        name="calendar_month",
    ),
]
