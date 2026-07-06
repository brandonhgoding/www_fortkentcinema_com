from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("screens", views.ScreenListView.as_view(), name="screens"),
    path("screens/new", views.ScreenCreateView.as_view(), name="screen_create"),
    path("screens/<int:pk>/edit", views.ScreenEditView.as_view(), name="screen_edit"),
    path("screens/<int:pk>/delete", views.ScreenDeleteView.as_view(), name="screen_delete"),
    path("engagements", views.EngagementsStubView.as_view(), name="engagements"),
]
