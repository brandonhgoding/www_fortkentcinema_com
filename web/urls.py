from django.urls import path

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
