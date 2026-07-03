from django.urls import path

from .views import AboutView, ClassicsView, HomeView, MembershipView, RentalsView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("membership/", MembershipView.as_view(), name="membership"),
    path("rentals/", RentalsView.as_view(), name="rentals"),
    path("about/", AboutView.as_view(), name="about"),
    path("classics/", ClassicsView.as_view(), name="classics"),
]
