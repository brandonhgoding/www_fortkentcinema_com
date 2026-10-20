"""The cinema's clock. Every "today", day boundary and calendar label on the
site is Eastern: the box office, not the visitor's device or the server."""
import datetime
from zoneinfo import ZoneInfo

CINEMA_TZ = ZoneInfo("America/New_York")


def business_date(when: datetime.datetime) -> datetime.date:
    """The Eastern calendar day a sale (or anything else) happened on."""
    return when.astimezone(CINEMA_TZ).date()
