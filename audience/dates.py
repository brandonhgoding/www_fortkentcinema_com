"""Calendar arithmetic for membership terms.

Hand-rolled rather than pulled from dateutil: that package is only present
as a transitive dependency of the optional boto3 stack, and this is the one
calculation we need.
"""

import calendar
import datetime


def add_months(start: datetime.date, months: int) -> datetime.date:
    """Return `start` advanced by `months`, clamped to the target month's length."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)
