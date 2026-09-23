"""Open Mic: when the next one is.

Much smaller than craft night or heckle night, because there is nothing to
look up. Those pages read a film out of the schedule; open mic has no film,
no booking and no Engagement row — it is the room, a microphone and a
sign-up sheet every Monday. So the only computed thing on the page is the
date, and it is computed for the same reason theirs are: "every Monday" is
a rule, and a typed date goes stale in public without anything breaking.
"""
import datetime

from web.constants import OPEN_MIC
from web.services.showtimes import CINEMA_TZ


def upcoming_nights(count=1, *, now=None):
    """The next `count` open mic nights, tonight's included until it ends.

    Rolls over at the END time rather than at midnight, unlike the monthly
    nights. Those only need a date; this one is weekly, so the question
    people bring to the page on a Monday evening is "is it on right now",
    and at 7:30 on a Monday the answer is tonight, not next week.
    """
    if now is None:
        now = datetime.datetime.now(CINEMA_TZ)
    local = now.astimezone(CINEMA_TZ)
    today = local.date()

    days_ahead = (OPEN_MIC["weekday"] - today.weekday()) % 7
    first = today + datetime.timedelta(days=days_ahead)
    if first == today and local.time() >= OPEN_MIC["end_time"]:
        first += datetime.timedelta(days=7)

    return [first + datetime.timedelta(weeks=n) for n in range(count)]
