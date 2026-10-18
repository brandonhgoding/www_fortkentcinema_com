from django.urls import path

from tickets import views

app_name = "tickets"

urlpatterns = [
    path("<int:pk>/", views.buy, name="buy"),
    path("order/<str:token>/", views.order, name="order"),
]
