from django.urls import path

from .views import (
    # AboutView,  # About page temporarily hidden (re-enable with the /about path below)
    CalendarMonthView,
    HomeView,
    MembershipView,
    MovieDetailView,
    RentalsView,
    SilentsSyncedEventView,
    ThanksView,
    VoteArchiveView,
    VoteCastView,
    VoteSubscribeView,
    VoteView,
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("membership/", MembershipView.as_view(), name="membership"),
    path("rentals/", RentalsView.as_view(), name="rentals"),
    # path("about/", AboutView.as_view(), name="about"),  # About page temporarily hidden — re-enable this + the AboutView import to restore /about
    # Square redirects here after a successful payment. noindex, unlinked,
    # and deliberately absent from the sitemap.
    path("thanks", ThanksView.as_view(), name="thanks"),
    # /vote/cast and /vote/subscribe must precede /vote/<slug>, or "cast"
    # would be matched as a poll slug.
    path("vote", VoteView.as_view(), name="vote"),
    path("vote/cast", VoteCastView.as_view(), name="vote_cast"),
    path("vote/subscribe", VoteSubscribeView.as_view(), name="vote_subscribe"),
    path("vote/<slug:slug>", VoteArchiveView.as_view(), name="vote_archive"),
    # No trailing slash, matching /blog/<slug>: detail pages are slugless-suffix,
    # section pages (/membership/, /rentals/) keep theirs.
    path("movies/<slug:slug>", MovieDetailView.as_view(), name="movie_detail"),
    # One-off special event. Same slugless-suffix convention as /movies/<slug>;
    # the /events/ prefix is there so the next one doesn't need a new top-level
    # URL. Hardcoded rather than <slug:slug> — there is exactly one.
    path(
        "events/silents-synced-a-woman-of-the-world",
        SilentsSyncedEventView.as_view(),
        name="event_silents_synced",
    ),
    path(
        "calendar/<int:year>/<int:month>/",
        CalendarMonthView.as_view(),
        name="calendar_month",
    ),
]
