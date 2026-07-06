from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("screens", views.ScreensStubView.as_view(), name="screens"),
    path("engagements", views.EngagementsStubView.as_view(), name="engagements"),
]
