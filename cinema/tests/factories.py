import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime


def make_showtime(**over) -> Showtime:
    """A confirmed showing of "Dune" at 19:00 Eastern, seven days from today."""
    today = timezone.localdate()
    screen = Screen.objects.create(name="Screen 1", capacity=100)
    film = Film.objects.create(title="Dune", runtime_minutes=155)
    engagement = Engagement.objects.create(
        screen=screen,
        start_date=today,
        end_date=today + datetime.timedelta(days=14),
        status="CONFIRMED",
    )
    EngagementFilm.objects.create(engagement=engagement, film=film, position=1)
    starts_at = over.pop("starts_at", None)
    if starts_at is None:
        day = today + datetime.timedelta(days=7)
        starts_at = datetime.datetime.combine(
            day, datetime.time(19, 0), tzinfo=ZoneInfo("America/New_York")
        )
    return Showtime.objects.create(
        engagement=engagement, screen=screen, starts_at=starts_at, **over
    )
