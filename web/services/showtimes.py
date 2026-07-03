"""Date helpers for showtime display — Python port of the SPA's
src/utils/showtimeDates.js. All logic runs in the cinema's local timezone so
"today" and labels match the box office, not the visitor's device."""
import datetime
from zoneinfo import ZoneInfo

CINEMA_TZ = ZoneInfo("America/New_York")


def today_eastern():
    return datetime.datetime.now(CINEMA_TZ).date().isoformat()


def format_showtime_date(date_str, weekday="long", *, today=None):
    if today is None:
        today = today_eastern()
    if date_str == today:
        return "Today"
    d = datetime.date.fromisoformat(date_str)
    # %A = full weekday, %a = abbreviated; %b = abbreviated month; %-d = day, no pad
    fmt = "%A, %b %-d" if weekday == "long" else "%a, %b %-d"
    return d.strftime(fmt)


def upcoming_dates(showtimes, *, today=None):
    if not isinstance(showtimes, dict):
        return []
    if today is None:
        today = today_eastern()
    return sorted(k for k in showtimes if k >= today)
