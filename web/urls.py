from django.urls import path

from .views import HomeView, MembershipView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("membership/", MembershipView.as_view(), name="membership"),
]
