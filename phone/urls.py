from django.urls import path

from . import views

app_name = "phone"

urlpatterns = [
    path("voice/", views.incoming_call, name="incoming_call"),
    path("menu/", views.menu, name="menu"),
    path("voicemail/recorded/", views.voicemail_recorded, name="voicemail_recorded"),
    path("voicemail/status/", views.voicemail_status, name="voicemail_status"),
    path(
        "voicemail/transcribed/",
        views.voicemail_transcribed,
        name="voicemail_transcribed",
    ),
]
