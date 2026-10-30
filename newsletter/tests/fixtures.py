"""Shared fixtures: a weekend with one showtime, and a mixed subscriber list."""

import datetime

from audience.models import Subscriber
from cinema.models import Showtime
from web.tests.test_cinema_data import aware, make_engagement, make_film, make_screen

THURSDAY = datetime.date(2026, 11, 5)
SEND_TIME = aware(2026, 11, 5, 10, 0)


def weekend(title="Alpha"):
    """A confirmed run Nov 5-11, 2026 with one Sunday 8 PM showtime."""
    screen = make_screen()
    run = make_engagement(
        screen, [make_film(title, poster_url="http://p/a.jpg")],
        start=THURSDAY, end=THURSDAY + datetime.timedelta(days=6),
    )
    Showtime.objects.create(
        engagement=run, screen=screen, starts_at=aware(2026, 11, 8, 20, 0)
    )
    return run


def subscribers():
    """Two active addresses, one pending, one opted out. Returns the active two."""
    a, _ = Subscriber.objects.record("a@example.com", source="site")
    b, _ = Subscriber.objects.record("b@example.com", source="site")
    Subscriber.objects.request_signup("pending@example.com", "site")
    gone, _ = Subscriber.objects.record("gone@example.com", source="site")
    gone.unsubscribe()
    return a, b
