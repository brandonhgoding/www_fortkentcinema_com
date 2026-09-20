import calendar
import datetime
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from audience.models import MembershipTier, Subscriber
from blog.models import BlogPost
from cinema import voting as vote_engine
from cinema.models import (
    Engagement,
    EngagementStatus,
    Film,
    Poll,
    PollStatus,
    StudioTitle,
)
from web.constants import (
    FILM_HISTORY_VIDEO,
    SPONSORED_SCREENING,
    MEMBERSHIP_FAQ,
    SAVOY_PLAYBILLS,
    SPONSORSHIP_FAQ,
    SPONSORSHIP_POPCORN_CAP,
    SPONSORSHIP_SHOWCASE,
    SPONSORSHIP_TIERS,
)
from web.forms import SponsorshipInquiryForm
from web.services.cinema_data import (
    CINEMA_TZ,
    _format_runtime,
    _format_showtime,
    get_now_showing,
    get_coming_soon,
    get_calendar_month,
    get_film_page,
)
from web.services.showtimes import (
    today_eastern,
    format_showtime_date,
    upcoming_dates,
)
from web.services import voting as vote_service


class HomeView(TemplateView):
    template_name = "web/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        now_showing = get_now_showing()
        ctx["now_showing"] = now_showing
        coming_soon = get_coming_soon()
        ctx["coming_soon"] = coming_soon

        # Initial month for the lazy-loaded ComingSoon calendar: the earliest
        # coming-soon start_date's month, else the current Eastern month. Month
        # is 0-based to match get_calendar_month / the SPA (calendar_month url).
        initial_year, initial_month = _initial_calendar_month(coming_soon)
        ctx["initial_year"] = initial_year
        ctx["initial_month"] = initial_month

        # Sponsored-screening banner. None unless a sponsored run is on, so
        # the banner retires itself on the booking's last day.
        ctx["sponsored"] = sponsored_screening()

        # Self-expiring vote CTA: None unless a poll is OPEN, so the banner
        # retires itself when the round closes.
        ctx["vote_poll"] = vote_service.current_poll()

        # Home blog teaser: latest 6 posts, deterministically ordered. Six is
        # what the teaser grid lays out evenly — three across on a desktop,
        # two on a tablet, one on a phone — so no row is ever left half full.
        ctx["recent_posts"] = (
            BlogPost.objects.select_related("author", "category")
            .order_by("-post_date", "-id")[:6]
        )

        # The sponsor CTA says "From $N". N is the cheapest tier rather than a
        # typed number, so the home page cannot drift away from the prices on
        # /sponsor/ when a tier is repriced.
        ctx["sponsorship_from_price"] = min(t["price"] for t in SPONSORSHIP_TIERS)

        # Hero marquee bulbs: 17 across top/bottom, 5 down each side (Hero.jsx).
        ctx["hero_top_bulbs"] = range(17)
        ctx["hero_side_bulbs"] = range(5)

        # Now Showing date navigation. Alpine only toggles which date is
        # visible, so every date + its label must be present in the DOM.
        today = today_eastern()

        date_keys = set()
        for movie in now_showing:
            for date in upcoming_dates(movie.get("showtimes"), today=today):
                date_keys.add(date)
            # Per-movie upcoming dates (key/label/times) for the schedule cards
            # and the per-date showtime blocks in the desktop movie card.
            ups = upcoming_dates(movie.get("showtimes"), today=today)
            movie["upcoming"] = [
                {
                    "key": d,
                    "label": format_showtime_date(d, weekday="short", today=today),
                    "times": movie["showtimes"][d],
                }
                for d in ups
            ]
            movie["dates_json"] = json.dumps(ups)

        ns_dates = sorted(date_keys)
        ns_dates_labeled = [
            {"key": d, "label": format_showtime_date(d, today=today)}
            for d in ns_dates
        ]
        today_index = ns_dates.index(today) if today in ns_dates else 0

        ctx["ns_dates"] = ns_dates
        ctx["ns_dates_labeled"] = ns_dates_labeled
        ctx["ns_today"] = today
        ctx["ns_today_index"] = today_index
        ctx["ns_dates_json"] = json.dumps(ns_dates)
        ctx["ns_labels_json"] = json.dumps([d["label"] for d in ns_dates_labeled])
        ctx["ns_today_label"] = (
            ns_dates_labeled[today_index]["label"] if ns_dates_labeled else ""
        )

        return ctx


def sponsored_screening():
    """The sponsored run currently on, or None.

    Read from the catalog rather than restated. SPONSORED_SCREENING names the
    film and the business that paid for it; everything else — title, dates,
    showtimes, poster, trailer — comes from the Engagement and its Showtime
    rows. That is what stops this banner and Now Showing from disagreeing, and
    what lets the booking's own `end_date` retire the banner with no commit.

    Every miss returns None rather than raising: the homepage must not 500
    because a slug moved or a run was cancelled.
    """
    config = SPONSORED_SCREENING
    if not config:
        return None

    film = Film.objects.filter(slug=config["film_slug"]).first()
    if film is None:
        return None

    engagement = (
        Engagement.objects.filter(
            engagement_films__film=film,
            status=EngagementStatus.CONFIRMED,
            end_date__gte=timezone.localdate(),
        )
        .order_by("start_date")
        .first()
    )
    if engagement is None:
        return None

    # Grouped in one pass; `showtimes` is ordered by starts_at, so a day is
    # closed as soon as the next one begins.
    days: list[dict] = []
    for showtime in engagement.showtimes.filter(is_cancelled=False):
        local_date = showtime.starts_at.astimezone(CINEMA_TZ).date()
        if not days or days[-1]["date"] != local_date:
            days.append({"date": local_date, "times": []})
        days[-1]["times"].append(_format_showtime(showtime.starts_at))

    return {
        "film": film,
        "engagement": engagement,
        "sponsor": config["sponsor"],
        "eyebrow": config.get("eyebrow", ""),
        "admission": config.get("admission", ""),
        "days": days,
        "url": film.get_absolute_url(),
    }


def _initial_calendar_month(coming_soon):
    """Return (year, month0) for the ComingSoon calendar's initial view: the
    month of the earliest coming_soon `start_date` (YYYY-MM-DD), else the
    current Eastern month. `month0` is 0-based."""
    start_dates = [
        m.get("start_date") for m in (coming_soon or []) if m.get("start_date")
    ]
    if start_dates:
        try:
            earliest = min(start_dates)
            d = datetime.date.fromisoformat(earliest)
            return d.year, d.month - 1
        except Exception:
            pass
    now = datetime.datetime.now(CINEMA_TZ)
    return now.year, now.month - 1


class CalendarMonthView(TemplateView):
    """HTMX fragment: the ComingSoon calendar for a single month, with prev/next
    month navigation. `month` is 0-based (matches get_calendar_month / api.js).

    This is a bare fragment — no <html>, no <head> — so a <meta name="robots">
    is impossible; the X-Robots-Tag header below is the only way to keep it out
    of the index. `nofollow` is the part that matters: the fragment carries
    prev/next links, and the year range used to be MINYEAR..MAXYEAR, so a crawler
    could walk roughly 120,000 URLs of thin content. CALENDAR_YEAR_RANGE bounds it
    for real, because the trap shouldn't depend on a crawler honouring a header.
    """

    template_name = "partials/calendar_month.html"

    # Nobody browses a cinema calendar three years out. Anything further is a
    # crawler, not a customer.
    CALENDAR_YEAR_RANGE = 2

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        year = int(kwargs["year"])
        month = int(kwargs["month"])  # 0-based

        this_year = timezone.localdate().year
        earliest = this_year - self.CALENDAR_YEAR_RANGE
        latest = this_year + self.CALENDAR_YEAR_RANGE

        if not (0 <= month <= 11) or not (earliest <= year <= latest):
            raise Http404("Invalid calendar month")

        cal_month = month + 1  # 1-based for date/calendar math
        first = datetime.date(year, cal_month, 1)
        days_in_month = calendar.monthrange(year, cal_month)[1]

        # Leading blank count: SPA uses JS Date.getDay() (Sunday=0). Python's
        # date.weekday() is Monday=0..Sunday=6; convert with (wd + 1) % 7.
        first_weekday = (first.weekday() + 1) % 7

        calendar_data = get_calendar_month(year, month)

        # Cells: leading None blanks, then each day annotated with its movies.
        cells = [{"day": None, "movies": None} for _ in range(first_weekday)]
        for d in range(1, days_in_month + 1):
            cells.append({"day": d, "movies": calendar_data.get(d)})

        # Prev/next (year, 0-based month), wrapping December<->January.
        prev_month = (month - 1) % 12
        prev_year = year - 1 if month == 0 else year
        next_month = (month + 1) % 12
        next_year = year + 1 if month == 11 else year

        ctx.update(
            {
                "year": year,
                "month": month,
                "month_label": first.strftime("%B %Y").upper(),
                "cells": cells,
                "prev_year": prev_year,
                "prev_month": prev_month,
                "next_year": next_year,
                "next_month": next_month,
            }
        )
        return ctx


class MembershipView(TemplateView):
    template_name = "web/membership.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tiers"] = (
            MembershipTier.objects.filter(show_on_membership_page=True)
            .prefetch_related("benefits")
        )
        ctx["faqs"] = MEMBERSHIP_FAQ
        return ctx


class RentalsView(TemplateView):
    template_name = "web/rentals.html"


class AboutView(TemplateView):
    template_name = "web/about.html"


class ThanksView(TemplateView):
    """/thanks?tier=<slug> — where Square redirects after a payment succeeds.

    This is the only place a `purchase` event with real money is fired. An
    outbound click on "Join" is intent, not revenue: someone who clicks through
    and then abandons the Square checkout has not paid us, and attaching a value
    to that click would make GA4 report sales that never happened.

    The value is looked up server-side from the tier record by slug and is
    never read from the query string, so it can't be forged by editing the URL.

    An unknown or missing tier (gift cards, whose amount is variable, redirect
    here without one) renders a generic thank-you and fires nothing at all —
    better than a garbage event.

    Known limitation: this trusts the redirect. Someone visiting /thanks?tier=x
    directly would fire a purchase event. Verifying properly means a Square
    webhook and server-side payment validation, which is more machinery than a
    two-screen cinema needs. The page is noindex and linked from nowhere.
    """

    template_name = "web/thanks.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        slug = self.request.GET.get("tier", "")
        ctx["tier"] = MembershipTier.objects.filter(slug=slug).first()
        return ctx


class MovieDetailView(DetailView):
    """/movies/<slug>.

    Only films we have actually booked get a page. A film that has never been
    attached to an engagement has no showtimes and no run history — nothing but
    the TMDB blurb that every other cinema site also publishes — so it would be
    a duplicate-content page. Those films are catalog entries, not pages.

    A film that HAS been booked keeps its page forever: when a run ends the page
    becomes an archive rather than a 404. See web/redirects.py for what the last
    round of disappearing URLs cost us.
    """

    model = Film
    slug_field = "slug"
    slug_url_kwarg = "slug"
    context_object_name = "film"
    template_name = "web/movie_detail.html"

    def get_queryset(self):
        return (
            Film.objects.filter(engagements__isnull=False)
            .select_related("review", "review__author")
            .distinct()
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        film = ctx["film"]
        page = get_film_page(film)
        ctx["upcoming"] = page["upcoming"]
        ctx["runs"] = page["runs"]
        ctx["is_now_showing"] = bool(page["upcoming"])
        ctx["runtime_display"] = _format_runtime(film.runtime_minutes)
        # ISO-8601 duration for schema.org Movie.duration (120 -> PT120M).
        ctx["runtime_iso"] = f"PT{film.runtime_minutes}M" if film.runtime_minutes else ""
        ctx["now_showing"] = get_now_showing()
        # Internal linking: push crawlers (and people) between the movie
        # pages and /vote while this film is up for a vote.
        open_poll = vote_service.current_poll()
        ctx["on_ballot"] = (
            open_poll
            if open_poll and open_poll.options.filter(film=film).exists()
            else None
        )
        return ctx


def _vote_context(request, poll=None, message=""):
    """Shared context for every rendering of the vote panel."""
    voter_key = vote_engine.voter_key_from(request) or request.vote_key
    ctx = vote_service.resolve_vote_page(voter_key=voter_key, poll=poll)
    ctx["message"] = message
    return ctx


def _with_voter_cookie(response, request):
    """Set the voter cookie when the browser does not already carry one.

    httpOnly: nothing in the page needs to read it, and it is the only thing
    standing between one browser and a second vote.
    """
    if not vote_engine.voter_key_from(request):
        response.set_cookie(
            vote_engine.VOTER_COOKIE,
            request.vote_key,
            max_age=vote_engine.VOTER_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            secure=not settings.DEBUG,
        )
    return response


class VoteView(View):
    """/vote — the canonical, stable URL for the current round.

    This is the link pasted into Facebook, so it must stay valid across every
    round. Past rounds move to /vote/<slug>; see VoteArchiveView.
    """

    def get(self, request):
        request.vote_key = (
            vote_engine.voter_key_from(request) or vote_engine.new_voter_key()
        )
        ctx = _vote_context(request)
        response = render(request, "web/vote.html", ctx)
        return _with_voter_cookie(response, request)


class VoteArchiveView(View):
    """/vote/<slug> — a specific round.

    While a round is open its slug URL redirects to /vote, so exactly one page
    collects the shares and links.
    """

    def get(self, request, slug):
        poll = get_object_or_404(Poll, slug=slug)
        if poll.status == PollStatus.OPEN:
            return redirect("vote")
        if poll.status == PollStatus.DRAFT:
            raise Http404("No such poll.")

        request.vote_key = (
            vote_engine.voter_key_from(request) or vote_engine.new_voter_key()
        )
        ctx = _vote_context(request, poll=poll)
        return render(request, "web/vote.html", ctx)


class VoteCastView(View):
    """POST /vote/cast — record one ballot.

    HTMX gets the swapped panel back; a plain form POST is redirected to /vote
    so a refresh cannot re-submit.
    """

    def post(self, request):
        request.vote_key = (
            vote_engine.voter_key_from(request) or vote_engine.new_voter_key()
        )

        poll = vote_service.current_poll()
        option_id = request.POST.get("option")
        if not option_id:
            return HttpResponseBadRequest("No option selected.")

        message = ""
        if poll is None:
            message = "Voting has closed for this round."
        else:
            option = poll.options.filter(pk=option_id).first()
            if option is None:
                return HttpResponseBadRequest("Unknown option.")
            try:
                vote_engine.cast_vote(
                    poll,
                    option,
                    request.vote_key,
                    ip=vote_engine.client_ip(request),
                )
            except vote_engine.AlreadyVoted:
                message = "You've already voted in this round."
            except vote_engine.PollNotOpen:
                message = "Voting has closed for this round."
            except vote_engine.IPCapReached:
                message = "We've had a lot of votes from this connection already."
            except vote_engine.OptionMismatch:
                return HttpResponseBadRequest("Unknown option.")

        if request.headers.get("HX-Request"):
            ctx = _vote_context(request, message=message)
            response = render(request, "partials/vote_panel.html", ctx)
            return _with_voter_cookie(response, request)

        response = redirect("vote")
        return _with_voter_cookie(response, request)


class VoteSubscribeView(View):
    """POST /vote/subscribe — the ask that follows a vote.

    Deliberately says only that we'll let them know what won. Nothing here
    promises a cadence, because nothing in this project sends mail yet; the
    list is exported from the dashboard and sent by hand.
    """

    SOURCE = "poll_vote"

    def post(self, request):
        # Honeypot. A real person never fills this in; bots fill everything.
        if request.POST.get("website"):
            return render(
                request, "partials/vote_email_capture.html", {"subscribed": True}
            )

        email = (request.POST.get("email") or "").strip()
        try:
            validate_email(email)
        except ValidationError:
            return render(
                request,
                "partials/vote_email_capture.html",
                {"error": "That doesn't look like a valid email address."},
            )

        Subscriber.objects.record(
            email, source=self.SOURCE, ip=vote_engine.client_ip(request)
        )
        return render(
            request, "partials/vote_email_capture.html", {"subscribed": True}
        )


# Whitelist of sort keys. The querystring never reaches order_by directly.
SPONSOR_SORTS = {
    "title": "title",
    "-title": "-title",
    "year": "release_date",
    "-year": "-release_date",
    "runtime": "runtime_minutes",
    "-runtime": "-runtime_minutes",
}


class SponsorCatalogMixin:
    """The catalog query: filtering, sorting, pagination.

    Shared by the full page and by the htmx fragment so the two cannot
    drift. If they disagreed, the table you get while typing would differ
    from the one you get on refresh — and the decade hardening below would
    have to be right in two places instead of one.

    Server-side rather than a client-side table: the 1,140 available rows
    are ~266KB of HTML, and the catalog grows with every studio added. This
    shape survives 5,000 titles without a rewrite.
    """

    context_object_name = "titles"
    # 25 rows: a screenful you can scan without the table running past
    # the filters you just used and off the bottom of the page.
    paginate_by = 25

    def get_queryset(self):
        queryset = StudioTitle.objects.available().select_related("studio")

        query = (self.request.GET.get("q") or "").strip()
        if query:
            queryset = queryset.filter(title__icontains=query)

        rating = (self.request.GET.get("rating") or "").strip()
        if rating:
            queryset = queryset.filter(mpa_rating=rating)

        decade = (self.request.GET.get("decade") or "").strip()
        if decade.isascii() and decade.isdigit():
            start = int(decade)
            # isdigit() only rules out non-numeric junk; a huge or
            # out-of-range value (e.g. "9999999999999", "99999", "12000",
            # "0") still reaches Django's date machinery and raises
            # OverflowError/ValueError. No StudioTitle predates film itself
            # (1888) or lands past the next century, so 1800..2100 can't
            # reject a real decade. 2100 + 10 = 2110 is nowhere near
            # Python's date.MAXYEAR (9999), so the upper filter edge
            # (start + 10) can't overflow either.
            if 1800 <= start <= 2100:
                queryset = queryset.filter(
                    release_date__year__gte=start,
                    release_date__year__lt=start + 10,
                )

        sort = self.request.GET.get("sort") or "title"
        field = SPONSOR_SORTS.get(sort, "title")
        # pk breaks ties so pagination stays stable across pages.
        return queryset.order_by(field, "pk")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # The catalog partial renders the active sort into a hidden field the
        # filter form picks up. Both renderings need it: the fragment because
        # it is the only thing that refreshes that field, the full page
        # because it is the first thing to set it.
        ctx["sort"] = self.request.GET.get("sort", "title")
        return ctx


class SponsorView(SponsorCatalogMixin, ListView):
    """/sponsor/ — the pitch, the tiers, and what a business can pick from."""

    template_name = "web/sponsor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        available = StudioTitle.objects.available()

        years = available.exclude(release_date__isnull=True).values_list(
            "release_date__year", flat=True
        )
        ctx.update(
            {
                "tiers": SPONSORSHIP_TIERS,
                "showcase": SPONSORSHIP_SHOWCASE,
                "popcorn_cap": SPONSORSHIP_POPCORN_CAP,
                "total_count": available.count(),
                "ratings": sorted(
                    r for r in set(
                        available.values_list("mpa_rating", flat=True)
                    ) if r
                ),
                "decades": sorted({(year // 10) * 10 for year in years}, reverse=True),
                "q": self.request.GET.get("q", ""),
                "selected_rating": self.request.GET.get("rating", ""),
                "selected_decade": self.request.GET.get("decade", ""),
                "faqs": SPONSORSHIP_FAQ,
                # A bound form arrives via kwargs when SponsorInquiryView
                # re-renders after a validation error; otherwise start empty.
                "form": kwargs.get("form") or self.blank_form(),
                "sent": self.request.GET.get("sent") == "1",
                # Drives the noindex on ?films=all — see the block in
                # web/sponsor.html. One page, two renderings of the same
                # select, and only the light one belongs in the index.
                "films_all": self.wants_all_films,
            }
        )
        return ctx

    @property
    def wants_all_films(self) -> bool:
        """Whether to render all ~1,140 film options inline.

        The no-JavaScript escape hatch. With scripting on, the options are
        fetched from /sponsor/films on demand; with it off there is nothing to
        fetch with, so a plain link in <noscript> reloads the page with the
        full list in it.
        """
        return self.request.GET.get("films") == "all"

    def blank_form(self) -> SponsorshipInquiryForm:
        initial = {}
        # Lets a link name a film without any JavaScript — the same thing the
        # catalog's Sponsor links do through Alpine when it is available.
        film = self.request.GET.get("film")
        if film and film.isdigit():
            initial["studio_title"] = film
        return SponsorshipInquiryForm(
            initial=initial, defer_film_choices=not self.wants_all_films
        )


class SponsorCatalogView(SponsorCatalogMixin, ListView):
    """HTMX fragment: the sponsor catalog's rows, pagination, and empty state.

    Swapped into #sponsor-results when you type in the filters, sort a
    column, or page — so none of that reloads the page and throws you back
    to the top of it.

    Deliberately not a subclass of SponsorView: the tiers, the rating and
    decade choices, the total count, and the inquiry form are all page
    chrome this fragment never renders, and this endpoint runs on every
    pause in typing. It shares only the queryset.

    This is a bare fragment — no <html>, no <head> — so a <meta name="robots">
    is impossible; the X-Robots-Tag header is the only way to keep it out of
    the index. The full page at /sponsor/ is the indexable one, and it renders
    the same rows inline, so nothing is hidden from a crawler by living here.
    """

    template_name = "partials/sponsor_catalog.html"

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response


class SponsorFilmOptionsView(ListView):
    """GET /sponsor/films — the inquiry form's film <option> list.

    Exists so /sponsor/ can ship without it. The list is ~1,140 options and
    was 56KB of every page load, for a control most visitors never open.

    Unpaginated on purpose: this is one <select>, and a reader who opens it
    expects the whole catalog. Same noindex treatment as the catalog
    fragment — it is a bare fragment with no <head> to put a meta tag in, and
    /sponsor/ is the page that should rank.
    """

    template_name = "partials/sponsor_film_options.html"
    context_object_name = "titles"

    def get_queryset(self):
        return StudioTitle.objects.available().order_by("title", "pk")

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response


class SponsorInquiryView(SponsorView):
    """POST /sponsor/inquire.

    Saves the lead and says thank you. It does not email anyone, because
    nothing in this project can send mail — the dashboard list and the
    smart-alert count are the delivery mechanism.

    Subclasses SponsorView so a validation error can re-render the whole
    page with the bound form. The vote page gets away with returning a bare
    partial because it is driven by htmx; there is no htmx on this page, so
    a fragment would arrive as an unstyled document with no navigation.

    Success redirects rather than rendering, so a refresh cannot resubmit.
    """

    def get(self, request, *args, **kwargs):
        return redirect("sponsor")

    def post(self, request, *args, **kwargs):
        # Deferred here too, so the error re-render is as light as the first
        # paint. `defer_film_choices` only trims what gets rendered — the
        # queryset validation below still sees every available title.
        form = SponsorshipInquiryForm(
            request.POST, defer_film_choices=not self.wants_all_films
        )
        sent_url = f"{reverse('sponsor')}?sent=1#inquire"

        if form.is_bot:
            # Indistinguishable from success, so a bot learns nothing.
            return redirect(sent_url)

        if form.is_valid():
            inquiry = form.save(commit=False)
            inquiry.ip = vote_engine.client_ip(request)
            inquiry.save()
            return redirect(sent_url)

        # ListView needs object_list populated before get_context_data.
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class HistoryView(TemplateView):
    """/history/ — how Fort Kent has gone to the movies since 1917.

    Hand-authored prose rather than model-driven content: this is one page
    about one town's history and it is not going to grow rows. The playbills
    are the exception — they come from web.constants.SAVOY_PLAYBILLS so the
    owner can add the rest of the Historical Society's sheets without touching
    the template.

    Sourcing is deliberately visible on the page. Almost everything here comes
    from a single published article by an archivist, and a page about a real
    town's real families should show where it got that rather than assert it
    in its own voice.
    """

    template_name = "web/history.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["playbills"] = SAVOY_PLAYBILLS
        ctx["video"] = FILM_HISTORY_VIDEO
        return ctx
