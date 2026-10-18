from django.urls import path

from tickets import views

app_name = "tickets"

urlpatterns = [
    path("<int:pk>/", views.BuyView.as_view(), name="buy"),
    path("order/<str:token>/", views.OrderView.as_view(), name="order"),
    path("order/<str:token>/qr.png", views.order_qr, name="order_qr"),
]
