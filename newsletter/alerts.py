"""Did last Thursday's email go out? For the dashboard home's smart alerts."""

from __future__ import annotations

import datetime

from newsletter.models import Issue

THURSDAY = 3


def last_thursday(today: datetime.date) -> datetime.date | None:
    """This week's Thursday once the week has moved past it (Friday to
    Sunday); None from Monday to Thursday, when there is nothing to miss yet."""
    if today.weekday() <= THURSDAY:
        return None
    return today - datetime.timedelta(days=today.weekday() - THURSDAY)


def missed(today: datetime.date) -> bool:
    """True when this week's Thursday has passed with no sent or skipped Issue."""
    week_of = last_thursday(today)
    if week_of is None:
        return False
    return not Issue.objects.filter(
        week_of=week_of, status__in=(Issue.Status.SENT, Issue.Status.SKIPPED)
    ).exists()
