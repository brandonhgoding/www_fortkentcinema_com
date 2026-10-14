from django.urls import path
from django.views.generic import RedirectView

from .list_signup import ListConfirmView, ListSignupView
from .views import (
    CalendarMonthView,
    HeckleNightView,
    HistoryView,
    HomeView,
    MembershipView,
    OpenMicView,
    RentalInquiryView,
    RentalsView,
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
    path("rentals/inquire", RentalInquiryView.as_view(), name="rentals_inquire"),
    # Trailing slash like the other section pages. "heckle-night" rather
    # than anything borrowing MST3K's name: the URL says what the night is
    # and belongs to us.
    path("heckle-night/", HeckleNightView.as_view(), name="heckle_night"),
    path("open-mic/", OpenMicView.as_view(), name="open_mic"),
    path("history/", HistoryView.as_view(), name="history"),
    # Square redirects here after a successful payment. noindex, unlinked,
    # and deliberately absent from the sitemap.
    path("thanks", ThanksView.as_view(), name="thanks"),
    # Double opt-in: /subscribe emails a link, /subscribe/confirm/<token>
    # (the link) is what actually joins the list.
    path("subscribe", ListSignupView.as_view(), name="list_signup"),
    path(
        "subscribe/confirm/<str:token>",
        ListConfirmView.as_view(),
        name="list_confirm",
    ),
    # /vote/cast and /vote/subscribe must precede /vote/<slug>, or "cast"
    # would be matched as a poll slug.
    path("vote", VoteView.as_view(), name="vote"),
    path("vote/cast", VoteCastView.as_view(), name="vote_cast"),
    path("vote/subscribe", VoteSubscribeView.as_view(), name="vote_subscribe"),
    path("vote/<slug:slug>", VoteArchiveView.as_view(), name="vote_archive"),
    # The canonical vote and movie URLs have no trailing slash, but people
    # type and share them with one — every section page has one. APPEND_SLASH
    # only adds slashes, so without these the slashed forms were hard 404s.
    # Same treatment as /blog/<slug>/ in blog/urls_site.py.
    path("vote/", RedirectView.as_view(pattern_name="vote", permanent=True)),
    path(
        "vote/<slug:slug>/",
        RedirectView.as_view(pattern_name="vote_archive", permanent=True),
    ),
    path(
        "calendar/<int:year>/<int:month>/",
        CalendarMonthView.as_view(),
        name="calendar_month",
    ),
]
