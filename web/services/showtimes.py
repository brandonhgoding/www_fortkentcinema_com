"""Date helpers for showtime display — Python port of the SPA's
src/utils/showtimeDates.js. All logic runs in the cinema's local timezone so
"today" and labels match the box office, not the visitor's device."""
import datetime

from cinema.dates import CINEMA_TZ


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
