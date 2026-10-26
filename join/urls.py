from django.urls import path

from join import views

app_name = "join"

urlpatterns = [
    path("membership/join/<slug:slug>/", views.JoinView.as_view(), name="start"),
    path("membership/order/<str:token>/", views.OrderView.as_view(), name="order"),
]
