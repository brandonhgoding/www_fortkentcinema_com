"""The pre-sale challenge banner's on/off switch.

The challenge has a deadline; the banner shows through that day (Eastern,
like every date on the site) and is gone the next morning. Returns the
PRESALE_CHALLENGE dict while live, else None, so the template has one test.
"""

import datetime

from web.constants import PRESALE_CHALLENGE
from web.services.showtimes import today_eastern


def active_presale(today=None):
    if today is None:
        today = datetime.date.fromisoformat(today_eastern())
    if today > PRESALE_CHALLENGE["deadline"]:
        return None
    return PRESALE_CHALLENGE
