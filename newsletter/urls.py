from django.urls import path

from newsletter.views import UnsubscribeView

# No app_name: the name is global like list_signup and list_confirm, and the
# email's footer link reverses it from outside any namespace.
urlpatterns = [
    path(
        "unsubscribe/<uuid:token>", UnsubscribeView.as_view(), name="list_unsubscribe"
    ),
]
