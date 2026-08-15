import calendar
import datetime
import json

from django.http import Http404
from django.utils import timezone
from django.views.generic import DetailView, TemplateView

from blog.models import BlogPost
from cinema.models import Film
from web.services.cinema_data import (
    CINEMA_TZ,
    _format_runtime,
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

        # Home blog teaser: latest 3 posts, deterministically ordered.
        ctx["recent_posts"] = BlogPost.objects.select_related("author", "category").order_by("-post_date", "-id")[:3]

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


class RentalsView(TemplateView):
    template_name = "web/rentals.html"


class AboutView(TemplateView):
    template_name = "web/about.html"


class ThanksView(TemplateView):
    """/thanks — where Square redirects after a payment succeeds.

    Gift cards are the only thing that lands here now, and their amount is
    variable, so the page fires no `purchase` event: it renders a generic
    thank-you. It used to fire one for memberships, priced server-side from
    MEMBERSHIP by tier slug so the value couldn't be forged from the query
    string. The membership program was discontinued 2026-08-14 and that branch
    went with it, which means the site no longer reports revenue to GA4 — by
    design, not by breakage.

    Still noindex and linked from nowhere.
    """

    template_name = "web/thanks.html"


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
        return ctx
