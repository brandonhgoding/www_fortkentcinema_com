from django.urls import path

from . import (
    ad_inquiry_views,
    rental_inquiry_views,
    subscriber_views,
    views,
    voicemail_views,
)

app_name = "dashboard"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("films/search", views.FilmSearchView.as_view(), name="film_search"),
    path(
        "films/search/tmdb", views.FilmSearchTMDBView.as_view(), name="film_search_tmdb"
    ),
    path("films/from-tmdb", views.FilmFromTMDBView.as_view(), name="film_from_tmdb"),
    path("engagements", views.EngagementListView.as_view(), name="engagements"),
    path(
        "engagements/<int:pk>",
        views.EngagementDetailView.as_view(),
        name="engagement_detail",
    ),
    path(
        "engagements/new",
        views.EngagementCreateView.as_view(),
        name="engagement_create",
    ),
    path(
        "engagements/<int:pk>/edit",
        views.EngagementEditView.as_view(),
        name="engagement_edit",
    ),
    path(
        "engagements/<int:pk>/delete",
        views.EngagementDeleteView.as_view(),
        name="engagement_delete",
    ),
    path(
        "engagements/<int:pk>/status",
        views.EngagementStatusView.as_view(),
        name="engagement_status",
    ),
    path(
        "engagements/<int:pk>/square/retry",
        views.EngagementSquareRetryView.as_view(),
        name="engagement_square_retry",
    ),
    path(
        "engagements/<int:eng_pk>/showtimes/new",
        views.ShowtimeCreateView.as_view(),
        name="showtime_create",
    ),
    path(
        "engagements/<int:eng_pk>/showtimes/bulk",
        views.ShowtimeBulkView.as_view(),
        name="showtime_bulk",
    ),
    path(
        "showtimes/<int:pk>/edit",
        views.ShowtimeEditView.as_view(),
        name="showtime_edit",
    ),
    path(
        "showtimes/<int:pk>/delete",
        views.ShowtimeDeleteView.as_view(),
        name="showtime_delete",
    ),
    path(
        "subscribers",
        subscriber_views.SubscriberListView.as_view(),
        name="subscribers",
    ),
    path(
        "subscribers/export.csv",
        subscriber_views.SubscriberExportView.as_view(),
        name="subscribers_export",
    ),
    path(
        "rental-inquiries",
        rental_inquiry_views.RentalInquiryListView.as_view(),
        name="rental_inquiries",
    ),
    path(
        "rental-inquiries/<int:pk>/status",
        rental_inquiry_views.RentalInquiryStatusView.as_view(),
        name="rental_inquiry_status",
    ),
    path(
        "ad-inquiries",
        ad_inquiry_views.AdInquiryListView.as_view(),
        name="ad_inquiries",
    ),
    path(
        "ad-inquiries/<int:pk>/status",
        ad_inquiry_views.AdInquiryStatusView.as_view(),
        name="ad_inquiry_status",
    ),
    path("voicemails", voicemail_views.VoicemailListView.as_view(), name="voicemails"),
    path(
        "voicemails/<int:pk>/status",
        voicemail_views.VoicemailStatusView.as_view(),
        name="voicemail_status",
    ),
    path(
        "voicemails/<int:pk>/notes",
        voicemail_views.VoicemailNotesView.as_view(),
        name="voicemail_notes",
    ),
    path(
        "voicemails/<int:pk>/delete",
        voicemail_views.VoicemailDeleteView.as_view(),
        name="voicemail_delete",
    ),
    path(
        "voicemails/<int:pk>/audio",
        voicemail_views.VoicemailAudioView.as_view(),
        name="voicemail_audio",
    ),
]
