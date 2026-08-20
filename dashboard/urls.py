from django.urls import path

from . import poll_views, views

app_name = "dashboard"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("screens", views.ScreenListView.as_view(), name="screens"),
    path("screens/new", views.ScreenCreateView.as_view(), name="screen_create"),
    path("screens/<int:pk>/edit", views.ScreenEditView.as_view(), name="screen_edit"),
    path("screens/<int:pk>/delete", views.ScreenDeleteView.as_view(), name="screen_delete"),
    path("films/search", views.FilmSearchView.as_view(), name="film_search"),
    path("films/search/tmdb", views.FilmSearchTMDBView.as_view(), name="film_search_tmdb"),
    path("films/from-tmdb", views.FilmFromTMDBView.as_view(), name="film_from_tmdb"),
    path("engagements", views.EngagementListView.as_view(), name="engagements"),
    path("engagements/<int:pk>", views.EngagementDetailView.as_view(), name="engagement_detail"),
    path("engagements/new", views.EngagementCreateView.as_view(), name="engagement_create"),
    path("engagements/<int:pk>/edit", views.EngagementEditView.as_view(), name="engagement_edit"),
    path("engagements/<int:pk>/delete", views.EngagementDeleteView.as_view(), name="engagement_delete"),
    path("engagements/<int:pk>/status", views.EngagementStatusView.as_view(), name="engagement_status"),
    path(
        "engagements/<int:pk>/social/<slug:platform>.png",
        views.EngagementSocialCardView.as_view(),
        name="engagement_social_card",
    ),
    path("engagements/<int:eng_pk>/showtimes/new", views.ShowtimeCreateView.as_view(), name="showtime_create"),
    path("engagements/<int:eng_pk>/showtimes/bulk", views.ShowtimeBulkView.as_view(), name="showtime_bulk"),
    path("showtimes/<int:pk>/edit", views.ShowtimeEditView.as_view(), name="showtime_edit"),
    path("showtimes/<int:pk>/delete", views.ShowtimeDeleteView.as_view(), name="showtime_delete"),
    path("polls", poll_views.PollListView.as_view(), name="polls"),
    path("polls/new", poll_views.PollCreateView.as_view(), name="poll_create"),
    path("polls/<int:pk>/edit", poll_views.PollEditView.as_view(), name="poll_edit"),
    path("polls/<int:pk>", poll_views.PollDetailView.as_view(), name="poll_detail"),
    path(
        "polls/<int:pk>/options/add",
        poll_views.PollOptionAddView.as_view(),
        name="poll_option_add",
    ),
    path(
        "polls/<int:pk>/options/<int:option_pk>/remove",
        poll_views.PollOptionRemoveView.as_view(),
        name="poll_option_remove",
    ),
    path(
        "polls/<int:pk>/options/<int:option_pk>/move",
        poll_views.PollOptionMoveView.as_view(),
        name="poll_option_move",
    ),
    path(
        "polls/<int:pk>/status",
        poll_views.PollStatusView.as_view(),
        name="poll_status",
    ),
    path(
        "polls/<int:pk>/announce",
        poll_views.PollAnnounceView.as_view(),
        name="poll_announce",
    ),
]
