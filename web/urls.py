from django.urls import path, re_path
from django.views.generic import RedirectView

from .list_signup import ListConfirmView, ListSignupView
from .views import (
    AdInquiryView,
    AdvertiseView,
    CalendarMonthView,
    HomeView,
    RentalInquiryView,
    RentalsView,
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("rentals/", RentalsView.as_view(), name="rentals"),
    path("rentals/inquire", RentalInquiryView.as_view(), name="rentals_inquire"),
    path("advertise/", AdvertiseView.as_view(), name="advertise"),
    path("advertise/inquire", AdInquiryView.as_view(), name="advertise_inquire"),
    # The address the pre-show "Your business here" slide prints: short
    # enough to type off the screen, and tagged so GA4 counts the visits the
    # screen sends. Temporary (302) so the tags can change without browsers
    # having cached the old ones.
    re_path(
        r"^ads/?$",
        RedirectView.as_view(
            url="/advertise/?utm_source=fort-kent-cinema&utm_medium=pre-show"
            "&utm_campaign=advertise",
            permanent=False,
        ),
        name="ads_short_link",
    ),
    # Double opt-in: /subscribe emails a link, /subscribe/confirm/<token>
    # (the link) is what actually joins the list.
    path("subscribe", ListSignupView.as_view(), name="list_signup"),
    path(
        "subscribe/confirm/<str:token>",
        ListConfirmView.as_view(),
        name="list_confirm",
    ),
    path(
        "calendar/<int:year>/<int:month>/",
        CalendarMonthView.as_view(),
        name="calendar_month",
    ),
]
