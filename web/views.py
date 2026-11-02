import calendar
import datetime

from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.client_ip import request_ip
from web.constants import (
    AD_ARTWORK_DEADLINE_DAY,
    AD_SLIDE_PRICE,
    AD_VIDEO_MAX_SECONDS,
    AD_VIDEO_PRICE,
    ADVERTISING_FAQ,
    RENTALS_FAQ,
)
from web.forms import AdInquiryForm, RentalInquiryForm
from web.services.cinema_data import (
    CINEMA_TZ,
    get_coming_soon,
    get_calendar_month,
    get_hero_films,
)
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
    """/llms.txt, a plain-text summary for AI assistants, served from the
    site root like robots.txt. It needs absolute URLs, so it carries the
    site's base URL."""

    template_name = "llms.txt"
    content_type = "text/plain; charset=utf-8"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["base"] = f"{self.request.scheme}://{self.request.get_host()}"
        ctx["ad_slide_price"] = AD_SLIDE_PRICE
        ctx["ad_video_price"] = AD_VIDEO_PRICE
        ctx["ad_video_max_seconds"] = AD_VIDEO_MAX_SECONDS
        return ctx


class RentalsView(TemplateView):
    template_name = "web/rentals.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # One list, two renderings: the visible FAQ and the FAQPage markup in
        # the head. Same arrangement as /advertise/.
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
