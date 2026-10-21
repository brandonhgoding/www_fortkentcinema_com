"""The cinema's clock. Every "today", day boundary and calendar label on the
site is Eastern: the box office, not the visitor's device or the server."""
import datetime
from zoneinfo import ZoneInfo

CINEMA_TZ = ZoneInfo("America/New_York")


def business_date(when: datetime.datetime) -> datetime.date:
    """The Eastern calendar day a sale (or anything else) happened on."""
    return when.astimezone(CINEMA_TZ).date()


def format_showtime(when: datetime.datetime) -> str:
    """A showtime as the listings and the phone line say it: "6:00 PM"."""
    return when.astimezone(CINEMA_TZ).strftime("%I:%M %p").lstrip("0")
