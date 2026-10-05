from django.urls import path

from .views import (
    CalendarMonthView,
    CraftNightView,
    HeckleNightView,
    HistoryView,
    HomeView,
    MembershipView,
    MovieDetailView,
    OpenMicView,
    RentalsView,
    SponsorCatalogView,
    SponsorFilmOptionsView,
    SponsorInquiryView,
    SponsorView,
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
    # Trailing slash, like the other section pages. "craft-night" rather
    # than "craft-cinema-night": the event keeps its full name, the URL
    # is the short thing people say and type.
    path("craft-night/", CraftNightView.as_view(), name="craft_night"),
    # Trailing slash like the other section pages. "heckle-night" rather
    # than anything borrowing MST3K's name: the URL says what the night is
    # and belongs to us.
    path("heckle-night/", HeckleNightView.as_view(), name="heckle_night"),
    path("open-mic/", OpenMicView.as_view(), name="open_mic"),
    path("sponsor/", SponsorView.as_view(), name="sponsor"),
    path("history/", HistoryView.as_view(), name="history"),
    path("sponsor/inquire", SponsorInquiryView.as_view(), name="sponsor_inquire"),
    # HTMX fragment behind the no-reload catalog. noindex/nofollow via
    # header, and absent from the sitemap: /sponsor/ is the real page.
    path("sponsor/catalog", SponsorCatalogView.as_view(), name="sponsor_catalog"),
    # The inquiry form's film <option> list, fetched on demand so /sponsor/
    # doesn't ship 56KB of it to everyone. noindex via header, absent from
    # the sitemap — same treatment as the catalog fragment above.
    path(
        "sponsor/films",
        SponsorFilmOptionsView.as_view(),
        name="sponsor_films",
    ),
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
    path(
        "calendar/<int:year>/<int:month>/",
        CalendarMonthView.as_view(),
        name="calendar_month",
    ),
]
