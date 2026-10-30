"""The online-ticket state of listed showtimes, shared by the home page's
chips, the calendar's dialogs and the Thursday email, so none can drift."""

from __future__ import annotations

import datetime

from django.urls import reverse
from django.utils import timezone

from boxoffice.gateway import square_enabled
from cinema.models import Showtime
from tickets import availability


def add_ticket_state(times, now: datetime.datetime | None = None) -> None:
    """Give each listed time dict its online-ticket state, in place.

    `ticket_url` is the buy page when the showing can sell now, and is kept
    when it is sold out online (the JSON-LD offer still names the page);
    otherwise it is "". `sold_out` is True only for a sold-out showing;
    `in_person` only for a showing whose online allowance is 0 on purpose.
    One for_showtimes() call for every chip: database only, never Square.
    """
    if now is None:
        now = timezone.now()
    times = list(times)
    ids = [t["showtime_id"] for t in times if t.get("showtime_id")]
    showtimes = Showtime.objects.filter(pk__in=ids).select_related(
        "engagement", "screen"
    )
    states = availability.for_showtimes(
        showtimes, now, square_enabled=square_enabled()
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
