import calendar
import datetime

from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, validate_email
from django.db.models import Min
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from audience.models import Member, MembershipTier, Subscriber
from blog.models import BlogPost
from boxoffice.gateway import square_enabled
from cinema import voting as vote_engine
from cinema.models import (
    Poll,
    PollStatus,
    Showtime,
    Vote,
)
from tickets import availability
from web.constants import (
    AD_ARTWORK_DEADLINE_DAY,
    AD_SLIDE_PRICE,
    AD_VIDEO_MAX_SECONDS,
    AD_VIDEO_PRICE,
    ADVERTISING_FAQ,
    HECKLE_NIGHT,
    HECKLE_NIGHT_FAQ,
    OPEN_MIC,
    OPEN_MIC_FAQ,
    FILM_HISTORY_VIDEO,
    MEMBERSHIP_FAQ,
    SAVOY_PLAYBILLS,
    RENTALS_FAQ,
)
from web.forms import AdInquiryForm, RentalInquiryForm
from web.list_signup import start_signup
from web.services.cinema_data import (
    CINEMA_TZ,
    get_coming_soon,
    get_calendar_month,
    get_hero_films,
)
from web.services.heckle_night import get_heckle_nights
from web.services.open_mic import upcoming_nights as upcoming_open_mics
from web.services.showtimes import (
    today_eastern,
    format_showtime_date,
)
from web.services import voting as vote_service


class HomeView(TemplateView):
    template_name = "web/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        coming_soon = get_coming_soon()
        ctx["coming_soon"] = coming_soon

        # Initial month for the lazy-loaded ComingSoon calendar: the earliest
        # coming-soon start_date's month, else the current Eastern month. Month
        # is 0-based to match get_calendar_month / the SPA (calendar_month url).
        initial_year, initial_month = _initial_calendar_month(coming_soon)
        ctx["initial_year"] = initial_year
        ctx["initial_month"] = initial_month

        # From the booth: the latest 3 posts, deterministically ordered, one
        # row of three image cards.
        ctx["recent_posts"] = (
            BlogPost.objects.published()
            .select_related("author", "category")
            .order_by("-post_date", "-id")[:3]
        )

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
        # Only rendered when nothing is booked (see partials/hero.html).
        ctx["hero_top_bulbs"] = range(17)
        ctx["hero_side_bulbs"] = range(5)

        today = today_eastern()

        # Hero: every film with a showing to come, the next one on the fold
        # and the rest a click away, each with its own times carrying the
        # ticket state the chips read. The hero is the listing, so this is
        # the one place a time renders. One for_showtimes() call for all.
        hero_films = get_hero_films()
        hero_times = []
        for film in hero_films:
            for slot in film["upcoming"]:
                slot["label"] = format_showtime_date(
                    slot["key"], weekday="short", today=today
                )
                hero_times.extend(slot["times"])
            film["date_label"] = format_showtime_date(
                film["date"], weekday="short", today=today
            )
        _add_ticket_state(hero_times)
        ctx["hero_films"] = hero_films

        # One schema.org ScreeningEvent per upcoming showtime, flattened here
        # so partials/home_jsonld.html is a single loop with one forloop.last.
        # A time dict with no "iso" (older fixtures, hand-built callers) is
        # skipped: an event with no startDate is worse than no event.
        ctx["ns_events"] = [
            {
                "movie": film,
                "iso": time["iso"],
                "ticket_url": time["ticket_url"],
                "sold_out": time["sold_out"],
                "in_person": time["in_person"],
            }
            for film in hero_films
            for slot in film["upcoming"]
            for time in slot["times"]
            if time.get("iso")
        ]

        return ctx


def _add_ticket_state(times):
    """Give each listed time dict its online-ticket state, in place.

    `ticket_url` is the buy page when the showing can sell now, and is kept
    when it is sold out online (the JSON-LD offer still names the page);
    otherwise it is "". `sold_out` is True only for a sold-out showing;
    `in_person` only for a showing whose online allowance is 0 on purpose.
    One for_showtimes() call for every chip: database only, never Square.
    """
    times = list(times)
    ids = [t["showtime_id"] for t in times if t.get("showtime_id")]
    showtimes = Showtime.objects.filter(pk__in=ids).select_related(
        "engagement", "screen"
    )
    states = availability.for_showtimes(
        showtimes, timezone.now(), square_enabled=square_enabled()
    )
    for time in times:
        state = states.get(time.get("showtime_id"))
        sold_out = state is not None and state.reason == "sold_out"
        has_page = state is not None and (state.purchasable or sold_out)
        time["ticket_url"] = (
            reverse("tickets:buy", args=[time["showtime_id"]]) if has_page else ""
        )
        time["sold_out"] = sold_out
        time["in_person"] = state is not None and state.reason == "in_person"


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

        # The key beside the grid: each film once, in the order it first
        # plays, with the first and last day it plays this month. Each
        # calendar poster carries its film's index into this list so hovering
        # a film in the key can pick out its days.
        films = []
        by_title = {}
        for d in sorted(calendar_data):
            for movie in calendar_data[d]:
                film = by_title.get(movie["title"])
                if film is None:
                    film = by_title[movie["title"]] = {
                        "index": len(films),
                        "title": movie["title"],
                        "slug": movie.get("slug", ""),
                        "poster": movie.get("poster", ""),
                        "first": d,
                        "last": d,
                    }
                    films.append(film)
                film["last"] = d
                movie["film_index"] = film["index"]
        month_abbr = first.strftime("%b")
        for film in films:
            film["dates"] = (
                f"{month_abbr} {film['first']}"
                if film["first"] == film["last"]
                else f"{month_abbr} {film['first']}\u2013{film['last']}"
            )

        # Cells: leading None blanks, then each day annotated with its movies.
        # Days before today are muted and today is ringed, so the grid reads
        # as "what's left this month" at a glance.
        today = timezone.localdate()
        cells = [{"day": None, "movies": None} for _ in range(first_weekday)]
        for d in range(1, days_in_month + 1):
            date = first.replace(day=d)
            cells.append(
                {
                    "day": d,
                    "movies": calendar_data.get(d),
                    "is_past": date < today,
                    "is_today": date == today,
                }
            )

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
                "month_name": first.strftime("%B"),
                "cells": cells,
                "films": films,
                "prev_year": prev_year,
                "prev_month": prev_month,
                "next_year": next_year,
                "next_month": next_month,
            }
        )
        return ctx


class LlmsTxtView(TemplateView):
    """/llms.txt, a plain-text summary for AI assistants. Like robots.txt it
    is served from the site root; unlike it, it needs the event
    constants, which the context processors don't carry."""

    template_name = "llms.txt"
    content_type = "text/plain; charset=utf-8"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["base"] = f"{self.request.scheme}://{self.request.get_host()}"
        ctx["open_mic"] = OPEN_MIC
        ctx["heckle_night"] = HECKLE_NIGHT
        return ctx


class MembershipView(TemplateView):
    template_name = "web/membership.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tiers"] = MembershipTier.objects.filter(
            show_on_membership_page=True
        ).prefetch_related("benefits")
        ctx["faqs"] = MEMBERSHIP_FAQ
        # With Square off every card sends people to the box office instead
        # of a join page that would only say the same thing.
        ctx["online_join"] = square_enabled()
        return ctx


class RentalsView(TemplateView):
    template_name = "web/rentals.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # One list, two renderings: the visible FAQ and the FAQPage markup in
        # the head. Same arrangement as /membership/.
        ctx["faqs"] = RENTALS_FAQ
        # A bound form arrives via kwargs when RentalInquiryView re-renders
        # after a validation error; otherwise start empty.
        ctx["form"] = kwargs.get("form") or RentalInquiryForm()
        ctx["sent"] = self.request.GET.get("sent") == "1"
        return ctx


class RentalInquiryView(RentalsView):
    """POST /rentals/inquire.

    Saves the lead and emails nobody (the dashboard list and the smart-alert
    count are the delivery mechanism). It re-renders the whole page on a
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


class AdvertiseView(TemplateView):
    template_name = "web/advertise.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # One list, two renderings: the visible FAQ and the FAQPage markup in
        # the head. Same arrangement as /rentals/.
        ctx["faqs"] = ADVERTISING_FAQ
        # The rates and terms come from web/constants.py so the cards, the
        # steps and the FAQ answers cannot disagree.
        ctx["slide_price"] = AD_SLIDE_PRICE
        ctx["video_price"] = AD_VIDEO_PRICE
        ctx["video_max_seconds"] = AD_VIDEO_MAX_SECONDS
        ctx["artwork_deadline_day"] = AD_ARTWORK_DEADLINE_DAY
        # A bound form arrives via kwargs when AdInquiryView re-renders after
        # a validation error; otherwise start empty.
        ctx["form"] = kwargs.get("form") or AdInquiryForm()
        ctx["sent"] = self.request.GET.get("sent") == "1"
        return ctx


class AdInquiryView(AdvertiseView):
    """POST /advertise/inquire.

    Saves the lead and emails nobody (the dashboard list is the delivery
    mechanism). It re-renders the whole page on a validation error because
    there is no htmx here, and it redirects on success so a refresh cannot
    resubmit. Same shape as RentalInquiryView.
    """

    def get(self, request, *args, **kwargs):
        return redirect("advertise")

    def post(self, request, *args, **kwargs):
        form = AdInquiryForm(request.POST)
        sent_url = f"{reverse('advertise')}?sent=1#inquire"

        if form.is_bot:
            # Indistinguishable from success, so a bot learns nothing.
            return redirect(sent_url)

        if form.is_valid():
            inquiry = form.save(commit=False)
            inquiry.ip = vote_engine.client_ip(request)
            inquiry.save()
            return redirect(sent_url)

        return self.render_to_response(self.get_context_data(form=form))


class HeckleNightView(TemplateView):
    """/heckle-night/ — the monthly bad-movie night the room talks over.

    Two computed things: the dates ("third Friday" is a rule) and the film
    on each one. The film lookup is parked until the Event model lands, so
    every night currently reads "Not booked yet". See web/services/heckle_night.py, and
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
        # A draft, or a round scheduled but not yet open, is not public: the
        # same nothing /vote/<slug> gives, so naming it here reveals nothing
        # (not even "wrong option" versus "right option").
        if poll is None or poll.status == PollStatus.DRAFT or not poll.has_started():
            return HttpResponseBadRequest("Unknown poll.")
        # Parsed like the poll id: junk is a 400, not a ValueError from the
        # ORM (a 500, and an error email, for anyone who posts "abc").
        option_id = _pk_or_none(request.POST.get("option"))
        if option_id is None:
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
