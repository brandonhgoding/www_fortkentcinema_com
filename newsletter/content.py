"""What goes in the Thursday email, assembled from the home page's services
so the email and the listing cannot disagree."""

from __future__ import annotations

import datetime

from django.utils import timezone

from blog.models import BlogPost
from boxoffice.site import base_url
from cinema.dates import CINEMA_TZ
from newsletter.models import UNSUBSCRIBE_PLACEHOLDER
from web.constants import SITE_CONFIG, TICKET_PRICES
from web.services.cinema_data import get_coming_soon, get_hero_films
from web.services.ticket_state import add_ticket_state

# Thursday through Sunday: today plus three more days.
WINDOW_DAYS = 3
COMING_SOON_CAP = 3
POST_MAX_AGE_DAYS = 7
SUBJECT_LEAD = "This weekend at the Cinema: "


def _local_date(dt: datetime.datetime) -> datetime.date:
    return dt.astimezone(CINEMA_TZ).date()


def window_for(now: datetime.datetime) -> tuple[datetime.date, datetime.date]:
    """The local dates the email covers, first and last inclusive."""
    today = _local_date(now)
    return today, today + datetime.timedelta(days=WINDOW_DAYS)


def day_label(d: datetime.date) -> str:
    return d.strftime("%A, %b %-d")


def opens_label(d: datetime.date) -> str:
    return d.strftime("%a, %b %-d")


def subject_for(films: list[dict]) -> str:
    titles = [f["title"] for f in films]
    if len(titles) > 2:
        return SUBJECT_LEAD + ", ".join(titles[:2]) + " and more"
    return SUBJECT_LEAD + ", ".join(titles)


def _films(now: datetime.datetime) -> list[dict]:
    first, last = window_for(now)
    films = []
    times = []
    for hero in get_hero_films(now):
        days = []
        for row in hero["upcoming"]:
            date = datetime.date.fromisoformat(row["key"])
            if first <= date <= last and row["times"]:
                days.append({"label": day_label(date), "times": row["times"]})
                times.extend(row["times"])
        if days:
            films.append({
                "title": hero["title"],
                "poster": hero["poster"],
                "rating": hero["rating"],
                "runtime": hero["runtime"],
                "is_free_for_members": hero["is_free_for_members"],
                "days": days,
            })
    add_ticket_state(times, now)
    site = base_url()
    for time in times:
        if time["ticket_url"]:
            time["ticket_url"] = site + time["ticket_url"]
    return films


def _coming_soon(now: datetime.datetime) -> list[dict]:
    cards = get_coming_soon(now)[:COMING_SOON_CAP]
    return [
        {
            "title": card["title"],
            "poster": card["poster"],
            "opens": opens_label(datetime.date.fromisoformat(card["start_date"])),
        }
        for card in cards
    ]


def _post(today: datetime.date) -> dict | None:
    post = BlogPost.objects.published().order_by("-post_date", "-created_at").first()
    if post is None:
        return None
    if (today - post.post_date).days > POST_MAX_AGE_DAYS:
        return None
    return {
        "title": post.title,
        "subtitle": post.subtitle,
        "url": base_url() + post.get_absolute_url(),
    }


def build_context(now: datetime.datetime | None = None) -> dict | None:
    """Everything the templates need, or None when no film has a showtime
    left in the window (the week is skipped; Coming Soon alone is no email)."""
    if now is None:
        now = timezone.now()
    films = _films(now)
    if not films:
        return None
    site = base_url()
    return {
        "films": films,
        "coming_soon": _coming_soon(now),
        "coming_soon_url": site + "/#coming-soon",
        "post": _post(_local_date(now)),
        "site_url": site,
        "cinema": SITE_CONFIG["cinema"],
        "ticket_prices": TICKET_PRICES,
        "unsubscribe_url": UNSUBSCRIBE_PLACEHOLDER,
    }
