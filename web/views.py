import json

from django.views.generic import TemplateView

from blog.models import BlogPost
from web.constants import MEMBERSHIP, MEMBERSHIP_FAQ
from web.services.leprinceos import get_now_showing, get_coming_soon
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
        ctx["coming_soon"] = get_coming_soon()

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


class MembershipView(TemplateView):
    template_name = "web/membership.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tiers"] = MEMBERSHIP
        ctx["faqs"] = MEMBERSHIP_FAQ
        return ctx
