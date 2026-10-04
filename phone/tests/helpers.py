import datetime
from zoneinfo import ZoneInfo

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.http import HttpResponse
from django.test import Client
from twilio.request_validator import RequestValidator

TOKEN = "test-auth-token"
EASTERN = ZoneInfo("America/New_York")


def at(
    year: int, month: int, day: int, hour: int, minute: int = 0
) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute, tzinfo=EASTERN)


def make_engagement(
    title: str,
    start: datetime.date,
    end: datetime.date,
    *,
    screen: Screen | None = None,
    status: str = "CONFIRMED",
    **extra: object,
) -> Engagement:
    screen = screen or Screen.objects.get_or_create(name="Screen 1", capacity=50)[0]
    engagement = Engagement.objects.create(
        screen=screen, start_date=start, end_date=end, status=status, **extra
    )
    film = Film.objects.create(title=title)
    EngagementFilm.objects.create(engagement=engagement, film=film, position=1)
    return engagement


def add_showtime(
    engagement: Engagement, starts_at: datetime.datetime, **extra: object
) -> Showtime:
    return Showtime.objects.create(engagement=engagement, starts_at=starts_at, **extra)


def post_signed(
    client: Client,
    path: str,
    data: dict[str, str],
    *,
    url: str | None = None,
    **headers: str,
) -> HttpResponse:
    """POST as Twilio would: signed over `url` (default: the test server URL)."""
    signature = RequestValidator(TOKEN).compute_signature(
        url or f"http://testserver{path}", data
    )
    return client.post(path, data, HTTP_X_TWILIO_SIGNATURE=signature, **headers)
