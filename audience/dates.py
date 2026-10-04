"""Calendar arithmetic for membership terms.

Hand-rolled rather than pulled in from a third-party date library: this is
the one calculation we need, and it is not worth a dependency.
"""

import calendar
import datetime


def add_months(start: datetime.date, months: int) -> datetime.date:
    """Return `start` advanced by `months`, clamped to the target month's length.

    Raises OverflowError past date.max (or before date.min), the same
    error `date + timedelta` raises, so callers have one thing to catch.
    """
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    if not datetime.MINYEAR <= year <= datetime.MAXYEAR:
        raise OverflowError("date value out of range")
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    """The first and last dates of a calendar month, both inclusive.

    Free admissions reset on the 1st, so "this month" is a closed date
    range rather than a comparison against a stored period. Returning both
    ends keeps the SQL annotation and the Python count honest about meaning
    the same thing.
    """
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, 1), datetime.date(year, month, last_day)
