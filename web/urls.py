from django.urls import path

from .views import AboutView, HomeView, MembershipView, RentalsView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("membership/", MembershipView.as_view(), name="membership"),
    path("rentals/", RentalsView.as_view(), name="rentals"),
    path("about/", AboutView.as_view(), name="about"),
]
