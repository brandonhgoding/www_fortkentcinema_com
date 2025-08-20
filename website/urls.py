from django.urls import include, path
from django.views.generic import TemplateView
from website import views as website_views

urlpatterns = [
    path("", website_views.HomePageTemplateView.as_view(), name="index"),
]
