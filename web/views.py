import calendar
import datetime
import json

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, validate_email
from django.db.models import Min
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from audience.models import Member, MembershipTier, Subscriber
from blog.models import BlogPost
from cinema import voting as vote_engine
from cinema.models import (
    Engagement,
    EngagementStatus,
    Film,
    Poll,
    PollStatus,
    StudioTitle,
    Vote,
)
from web.constants import (
    CRAFT_NIGHT,
    DONATION,
    CRAFT_NIGHT_FAQ,
    HECKLE_NIGHT,
    HECKLE_NIGHT_FAQ,
    OPEN_MIC,
    OPEN_MIC_FAQ,
    FILM_HISTORY_VIDEO,
    SPONSORED_SCREENING,
    MEMBERSHIP_FAQ,
    SAVOY_PLAYBILLS,
    RENTALS_FAQ,
    SPONSORSHIP_FAQ,
    SPONSORSHIP_SHOWCASE,
    SPONSORSHIP_TIERS,
)
from web.forms import RentalInquiryForm, SponsorshipInquiryForm
from web.list_signup import start_signup
from web.services.cinema_data import (
    CINEMA_TZ,
    _format_runtime,
    _format_showtime,
    get_now_showing,
    get_coming_soon,
    get_calendar_month,
    get_film_page,
)
from web.services.craft_night import get_craft_nights
from web.services.heckle_night import get_heckle_nights
from web.services.open_mic import upcoming_nights as upcoming_open_mics
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

        # Self-expiring vote CTAs: one per round that is OPEN and inside its
        # voting window, so each banner retires itself when its round closes.
        ctx["vote_polls"] = vote_service.open_polls()

        # Donate link in the Support strip. The partial renders nothing while
        # DONATION["url"] is blank, which is how it shipped ahead of the Square
        # item — a Donate link pointing nowhere never went live.
        ctx["donation"] = DONATION

        # Our story: the latest 3 posts, deterministically ordered. They sit
        # beside the history card, so three posts make a row of four cards.
        ctx["recent_posts"] = (
            BlogPost.objects.published()
            .select_related("author", "category")
            .order_by("-post_date", "-id")[:3]
        )

        # The Support strip's sponsor link says "from $N". N is the cheapest
        # tier rather than a typed number, so the home page cannot drift away
        # from the prices on /sponsor/ when a tier is repriced.
        ctx["sponsorship_from_price"] = min(t["price"] for t in SPONSORSHIP_TIERS)

        # Membership band: "From $N a year" is the cheapest tier the public
        # membership page lists, so a retired (unlisted) cheaper tier cannot
        # set the price. Only 12-month tiers count: duration_months is
        # editable, and a cheaper 6-month tier would make "a year" false.
        # None with no listed 12-month tier; the band drops the line.
        ctx["membership_from_price"] = MembershipTier.objects.filter(
            show_on_membership_page=True, duration_months=12
        ).aggregate(Min("price"))["price__min"]

        # Hero member count: people, not terms. Member.objects.active() is
        # DISTINCT on the member, so a renewal overlapping the term it
        # replaces still counts once, and .count() keeps it to one query.
        ctx["member_count"] = Member.objects.active().count()

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
            {"key": d, "label": format_showtime_date(d, today=today)} for d in ns_dates
        ]
        today_index = ns_dates.index(today) if today in ns_dates else 0

        ctx["ns_dates"] = ns_dates
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
        ctx["tiers"] = MembershipTier.objects.filter(
            show_on_membership_page=True
        ).prefetch_related("benefits")
        ctx["faqs"] = MEMBERSHIP_FAQ
        return ctx


class RentalsView(TemplateView):
    template_name = "web/rentals.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # One list, two renderings: the visible FAQ and the FAQPage markup in
        # the head. Same arrangement as /membership/ and /sponsor/.
        ctx["faqs"] = RENTALS_FAQ
        # A bound form arrives via kwargs when RentalInquiryView re-renders
        # after a validation error; otherwise start empty.
        ctx["form"] = kwargs.get("form") or RentalInquiryForm()
        ctx["sent"] = self.request.GET.get("sent") == "1"
        return ctx


class RentalInquiryView(RentalsView):
    """POST /rentals/inquire.

    The rentals twin of SponsorInquiryView, and for the same reasons: it
    saves the lead and emails nobody (the dashboard list and the smart-alert
    count are the delivery mechanism), it re-renders the whole page on a
    validation error because there is no htmx here, and it redirects on
    success so a refresh cannot resubmit.
    """

    def get(self, request, *args, **kwargs):
        return redirect("rentals")

    def post(self, request, *args, **kwargs):
        form = RentalInquiryForm(request.POST)
        sent_url = f"{reverse('rentals')}?sent=1#inquire"

        if form.is_bot:
            # Indistinguishable from success, so a bot learns nothing.
            return redirect(sent_url)

        if form.is_valid():
            inquiry = form.save(commit=False)
            inquiry.ip = vote_engine.client_ip(request)
            inquiry.save()
            return redirect(sent_url)

        return self.render_to_response(self.get_context_data(form=form))


class CraftNightView(TemplateView):
    """/craft-night/ — the standing monthly craft screening.

    Two things on this page come from rows rather than from prose: the dates
    (computed, because "last Tuesday" is a rule) and the film on each one
    (read from the schedule, so this page and Now Showing cannot disagree).
    See web/services/craft_night.py for why neither is typed in.

    Most listed nights will have no film yet — the last Tuesday of the month
    is further out than we book. That is the expected state, and the
    template renders it as "not booked yet" rather than hiding the date.
    """

    template_name = "web/craft_night.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["craft_night"] = CRAFT_NIGHT
        nights = get_craft_nights()
        ctx["nights"] = nights
        # The hero needs the next one on its own. nights is never empty —
        # upcoming_nights() walks the calendar forward until it has enough —
        # but the guard costs nothing and a 500 on the hero costs the page.
        ctx["next_night"] = nights[0] if nights else None
        # One list, two renderings: the visible FAQ and the FAQPage markup
        # in the head. Same arrangement as /rentals/ and /sponsor/.
        ctx["faqs"] = CRAFT_NIGHT_FAQ
        return ctx


class HeckleNightView(TemplateView):
    """/heckle-night/ — the monthly bad-movie night the room talks over.

    Same two computed things as /craft-night/: the dates ("third Friday" is
    a rule) and the film on each one (read from the schedule, so this page
    and Now Showing cannot disagree). See web/services/heckle_night.py, and
    note the one difference — nothing before HECKLE_NIGHT["starts_on"]
    renders, because this night has never run and the rule alone would
    advertise a date nobody planned.

    Most listed nights will have no film yet. That is the expected state,
    and the template renders it as "not booked yet" rather than hiding the
    date.
    """

    template_name = "web/heckle_night.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heckle_night"] = HECKLE_NIGHT
        nights = get_heckle_nights()
        ctx["nights"] = nights
        # The hero needs the next one on its own. nights is never empty —
        # upcoming_nights() walks the calendar forward until it has enough —
        # but the guard costs nothing and a 500 on the hero costs the page.
        ctx["next_night"] = nights[0] if nights else None
        # One list, two renderings: the visible FAQ and the FAQPage markup
        # in the head. Same arrangement as /craft-night/ and /rentals/.
        ctx["faqs"] = HECKLE_NIGHT_FAQ
        return ctx


class OpenMicView(TemplateView):
    """/open-mic/ — every Monday in the Century auditorium.

    No film and no booking behind it, so unlike the monthly nights the only
    computed thing is the next date. See web/services/open_mic.py.
    """

    template_name = "web/open_mic.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["open_mic"] = OPEN_MIC
        now = datetime.datetime.now(CINEMA_TZ)
        next_night = upcoming_open_mics(1, now=now)[0]
        ctx["next_night"] = next_night
        # "Tonight" rather than a date, on a Monday before 9 PM.
        ctx["next_is_tonight"] = next_night == now.date()
        # One list, two renderings: the visible FAQ and the FAQPage markup
        # in the head. Same arrangement as /heckle-night/ and /craft-night/.
        ctx["faqs"] = OPEN_MIC_FAQ
        return ctx


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
        return Film.objects.with_page().select_related("review", "review__author")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        film = ctx["film"]
        page = get_film_page(film)
        ctx["upcoming"] = page["upcoming"]
        ctx["runs"] = page["runs"]
        ctx["is_now_showing"] = bool(page["upcoming"])
        ctx["runtime_display"] = _format_runtime(film.runtime_minutes)
        # ISO-8601 duration for schema.org Movie.duration (120 -> PT120M).
        ctx["runtime_iso"] = (
            f"PT{film.runtime_minutes}M" if film.runtime_minutes else ""
        )
        ctx["now_showing"] = get_now_showing()
        # Internal linking: push crawlers (and people) between the movie
        # pages and the round's page while this film is up for a vote.
        ctx["on_ballot"] = next(
            (
                poll
                for poll in vote_service.open_polls()
                if poll.options.filter(film=film).exists()
            ),
            None,
        )
        return ctx


# Signs the vote behind the mailing-list ask on the thanks screen, so the
# only address that can be subscribed is the one that just voted. A day is
# plenty: the ask is answered on the spot or not at all.
_SUBSCRIBE_SALT = "vote-subscribe"
_SUBSCRIBE_MAX_AGE = 60 * 60 * 24

# Signs the vote just cast so the next ballot can reuse its address without
# asking again: the thanks screen puts it in the inline ballot for the next
# round and on the links to the rounds after that. It is a convenience, not
# an identity: a bad or stale token just means typing the address again.
# Separate salt from the subscribe token, so one can never stand in for the
# other. A day, like the subscribe token: nobody chains rounds across days.
_VOTER_SALT = "vote-voter"
_VOTER_MAX_AGE = 60 * 60 * 24


def _voter_token(vote) -> str:
    return signing.dumps(vote.pk, salt=_VOTER_SALT)


def _voter_from_token(raw) -> Vote | None:
    """The vote a carry token names, or None for anything but a good one.

    None covers a missing, forged or expired token, a vote since deleted,
    and a vote with no address (cast before the address was required): in
    every case the ballot falls back to asking for the address.
    """
    if not raw:
        return None
    try:
        vote_pk = signing.loads(raw, salt=_VOTER_SALT, max_age=_VOTER_MAX_AGE)
    except signing.BadSignature:
        return None
    vote = Vote.objects.filter(pk=vote_pk).first()
    if vote is None or not vote.email:
        return None
    return vote


def _vote_context(
    poll=None, vote=None, message="", form=None, subscribed=False, voter=None
):
    """Shared context for every rendering of the vote panel.

    `vote` is the ballot just cast. `form` carries a rejected ballot back
    to the template: what was typed and why it was refused, so nobody has
    to fill it in twice. `subscribed` is True once the thanks screen's
    mailing-list ask has been accepted. `voter` is an earlier vote whose
    address the ballot on this page should reuse; after a vote it is the
    vote itself, so the next round's ballot already knows the address.
    """
    ctx = vote_service.resolve_vote_page(poll=poll, vote=vote)
    ctx["message"] = message
    ctx["form"] = form or {}
    ctx["subscribed"] = subscribed
    # The vote just cast outranks the one that carried the address here: same
    # address, but a fresh signature, so a long chain never runs out the clock.
    voter = vote or voter
    ctx["voter"] = voter
    ctx["voter_token"] = _voter_token(voter) if voter else ""
    # The ask appears only for an address we have never heard from: not on
    # the list, and not someone who opted out, who must not be asked again.
    ctx["offer_subscribe"] = bool(
        vote
        and vote.email
        and not subscribed
        and not Subscriber.objects.filter(email=vote.email).exists()
    )
    ctx["subscribe_token"] = (
        signing.dumps(vote.pk, salt=_SUBSCRIBE_SALT) if ctx["offer_subscribe"] else ""
    )
    return ctx


def _pk_or_none(raw):
    """An integer primary key from POST data, or None for blank or junk."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _clean_ballot_email(raw: str) -> str:
    """The address as we store it, or a ValidationError.

    validate_email allows 320 characters; the column holds 254, and Postgres
    refuses the INSERT rather than truncating it.
    """
    email = (raw or "").strip()
    validate_email(email)
    MaxLengthValidator(Vote.EMAIL_MAX_LENGTH)(email)
    return email.lower()


class VoteView(View):
    """/vote — the stable URL for whatever is being voted on.

    This is the link pasted into Facebook, so it must stay valid across every
    round. One open round shows its ballot here; several show a list, each
    linking to its own /vote/<slug>, which is also where past rounds live.
    """

    def get(self, request):
        return render(request, "web/vote.html", _vote_context())


class VoteArchiveView(View):
    """/vote/<slug> — a specific round, open or decided.

    An open round renders its ballot here too, since more than one can be
    open and each needs a link of its own.
    """

    def get(self, request, slug):
        poll = get_object_or_404(Poll, slug=slug)
        if poll.status == PollStatus.DRAFT or not poll.has_started():
            raise Http404("No such poll.")
        # ?voter=<token> arrives from the thanks screen of another round and
        # saves typing the address again. Anything else is simply ignored.
        voter = _voter_from_token(request.GET.get("voter"))
        return render(request, "web/vote.html", _vote_context(poll=poll, voter=voter))


class VoteCastView(View):
    """POST /vote/cast — record one ballot.

    The ballot asks for an email address, required: it is what keeps a
    round to one vote per person. The address stays on the vote and is
    reached, if at all, through the dashboard's per-poll export. It does
    not join the mailing list; that is a separate opt-in. Nothing in this
    project sends mail yet, so the copy never promises a cadence.

    The address comes typed in `email`, or carried by `token`: the signed
    vote from a round just voted in, so the next ballot does not ask again.
    The token wins when both are present, because it is the one the ballot
    showed as "voting as"; a token that fails to verify falls back to the
    plain ballot with a note, never a 400, since it was only a convenience.

    HTMX gets the swapped panel back. A plain form POST gets the whole page
    with the same panel: there is no cookie to carry "you voted" across a
    redirect, and a refresh that re-submits is harmless, since the address
    rule refuses it.
    """

    def post(self, request):
        # The ballot names its round: several can be open at once.
        poll = Poll.objects.filter(pk=_pk_or_none(request.POST.get("poll"))).first()
        if poll is None or poll.status == PollStatus.DRAFT:
            return HttpResponseBadRequest("Unknown poll.")
        option_id = request.POST.get("option")
        if not option_id:
            return HttpResponseBadRequest("No option selected.")

        # Honeypot. A real person never fills this in; bots fill everything.
        # Answered like a success so the bot learns nothing.
        if request.POST.get("website"):
            return self._respond(request, poll)

        raw_email = request.POST.get("email") or ""
        form = {"option": option_id, "email": raw_email.strip()}

        voter = None
        raw_token = request.POST.get("token") or ""
        if raw_token:
            voter = _voter_from_token(raw_token)
            if voter is None:
                return self._respond(
                    request,
                    poll,
                    message=(
                        "That link has expired — please enter your email "
                        "to cast this vote."
                    ),
                    form=form,
                )
            email = voter.email
        else:
            try:
                email = _clean_ballot_email(raw_email)
            except ValidationError:
                form["error"] = "That doesn't look like a valid email address."
                return self._respond(request, poll, form=form)

        option = poll.options.filter(pk=option_id).first()
        if option is None:
            return HttpResponseBadRequest("Unknown option.")

        message = ""
        vote = None
        try:
            vote = vote_engine.cast_vote(poll, option, email)
        except vote_engine.EmailAlreadyVoted:
            # Said at the top of the panel, not as a field error: it is an
            # answer, not a typo to fix. The ballot stays filled in case they
            # meant a different address.
            return self._respond(
                request,
                poll,
                message=(
                    "Sorry — you only get one vote per round, and that "
                    "email address has already cast one."
                ),
                form=form,
                voter=voter,
            )
        except vote_engine.PollNotOpen:
            message = "Voting has closed for this round."
        except vote_engine.OptionMismatch:
            return HttpResponseBadRequest("Unknown option.")

        return self._respond(request, poll, vote=vote, message=message, voter=voter)

    @staticmethod
    def _respond(request, poll, vote=None, message="", form=None, voter=None):
        ctx = _vote_context(
            poll=poll, vote=vote, message=message, form=form, voter=voter
        )
        if request.headers.get("HX-Request"):
            return render(request, "partials/vote_panel.html", ctx)
        return render(request, "web/vote.html", ctx)


class VoteSubscribeView(View):
    """POST /vote/subscribe — the mailing-list ask on the thanks screen.

    The ballot itself promises no email, so joining the list is a separate,
    explicit yes, confirmed by email before it takes effect. The request
    carries a signed vote id rather than an address: the only address that
    can be added is the one that just voted, and nobody can subscribe
    someone else by posting their email.
    """

    SOURCE = "poll_vote"

    def post(self, request):
        try:
            vote_pk = signing.loads(
                request.POST.get("token", ""),
                salt=_SUBSCRIBE_SALT,
                max_age=_SUBSCRIBE_MAX_AGE,
            )
        except signing.BadSignature:
            return HttpResponseBadRequest("That link has expired.")
        vote = Vote.objects.filter(pk=vote_pk).select_related("poll").first()
        if vote is None or not vote.email:
            return HttpResponseBadRequest("Unknown vote.")

        # Idempotent, and never re-adds an address that opted out. The
        # address only joins once its owner follows the emailed link.
        start_signup(request, vote.email, source=self.SOURCE, poll=vote.poll)
        ctx = _vote_context(poll=vote.poll, vote=vote, subscribed=True)
        if request.headers.get("HX-Request"):
            return render(request, "partials/vote_panel.html", ctx)
        return render(request, "web/vote.html", ctx)


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
                "total_count": available.count(),
                "ratings": sorted(
                    r for r in set(available.values_list("mpa_rating", flat=True)) if r
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
