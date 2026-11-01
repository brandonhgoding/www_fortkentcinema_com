import calendar
import datetime

from django.db.models import Min
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.client_ip import request_ip
from audience.models import Member, MembershipTier
from blog.models import BlogPost
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

        today = today_eastern()

        # Hero: every film with a showing to come, the next one on the fold
        # and the rest a click away, each with its own times. The hero is
        # the listing, so this is the one place a time renders.
        hero_films = get_hero_films()
        for film in hero_films:
            for slot in film["upcoming"]:
                slot["label"] = format_showtime_date(
                    slot["key"], weekday="short", today=today
                )
            film["date_label"] = format_showtime_date(
                film["date"], weekday="short", today=today
            )
        ctx["hero_films"] = hero_films

        # One schema.org ScreeningEvent per showtime the hero lists, flattened
        # here so partials/home_jsonld.html is a single loop with one
        # forloop.last. Only the hero lists times (Coming Soon does not commit
        # to them), so only its showings are marked up. A time dict with no
        # "iso" (older fixtures, hand-built callers) is skipped: an event with
        # no startDate is worse than no event.
        ctx["ns_events"] = _screening_events(
            [(film, "/#now-showing") for film in hero_films]
        )

        return ctx


def _screening_events(listed):
    """ScreeningEvent dicts for `listed` (film dict, section URL) pairs, in
    order, each showtime once. `section_url` is the offer's URL: the section
    that lists the showing, where the door prices are."""
    seen = set()
    events = []
    for film, section_url in listed:
        for slot in film.get("upcoming", ()):
            for time in slot["times"]:
                pk = time.get("showtime_id")
                if not time.get("iso") or (pk is not None and pk in seen):
                    continue
                seen.add(pk)
                events.append(
                    {
                        "movie": film,
                        "iso": time["iso"],
                        "section_url": section_url,
                    }
                )
    return events


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
            inquiry.ip = request_ip(request)
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
            inquiry.ip = request_ip(request)
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
