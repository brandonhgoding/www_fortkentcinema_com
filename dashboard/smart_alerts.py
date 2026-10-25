from __future__ import annotations

import datetime

from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as format_date


def build_smart_alerts(engagements, tomorrow_showtimes_count: int,
                       today: datetime.date,
                       new_rental_inquiries: int = 0,
                       new_ad_inquiries: int = 0,
                       new_link_requests: int = 0,
                       new_voicemails: int = 0,
                       square_pull_status: str | None = None,
                       square_sync_failures: int = 0,
                       square_membership_failures: int = 0,
                       ticket_failures: int = 0,
                       nearly_sold_out=(),
                       cancelled_with_orders=()) -> list[dict]:
    """Server-side port of the React useSmartAlerts hook.

    engagements: iterable of Engagement (all engagements).
    tomorrow_showtimes_count: number of showtimes scheduled for tomorrow.
    today: local date.
    nearly_sold_out: (showtime, sold, allowance) rows, see tickets.alerts.
    cancelled_with_orders: (showtime, sold orders) rows, see tickets.alerts.
    """
    engagements = list(engagements)
    alerts: list[dict] = []

    if tomorrow_showtimes_count == 0 and engagements:
        alerts.append({
            "id": "no-showtimes-tomorrow", "type": "warning",
            "perm": "cinema.view_showtime",
            "message": "No showtimes scheduled for tomorrow",
        })

    two_days = today + datetime.timedelta(days=2)
    for e in engagements:
        if e.status != "CONFIRMED":
            continue
        if today <= e.end_date <= two_days:
            days_left = (e.end_date - today).days
            unit = "day" if days_left == 1 else "days"
            alerts.append({
                "id": f"ending-soon-{e.id}", "type": "info",
                "perm": "cinema.view_engagement",
                "message": f"{e.title} ends in {days_left} {unit}",
            })

    draft_count = sum(1 for e in engagements if e.status == "DRAFT")
    if draft_count > 0:
        unit = "engagement" if draft_count == 1 else "engagements"
        alerts.append({
            "id": "draft-engagements", "type": "info",
            "perm": "cinema.view_engagement",
            "message": f"You have {draft_count} draft {unit} waiting to be confirmed",
        })

    if new_rental_inquiries > 0:
        unit = "inquiry" if new_rental_inquiries == 1 else "inquiries"
        alerts.append({
            "id": "new-rental-inquiries", "type": "info",
            "perm": "cinema.view_rentalinquiry",
            "message": f"You have {new_rental_inquiries} new rental {unit}",
            "url": reverse("dashboard:rental_inquiries") + "?status=NEW",
        })

    if new_ad_inquiries > 0:
        unit = "inquiry" if new_ad_inquiries == 1 else "inquiries"
        alerts.append({
            "id": "new-ad-inquiries", "type": "info",
            "perm": "cinema.view_adinquiry",
            "message": f"You have {new_ad_inquiries} new ad {unit}",
            "url": reverse("dashboard:ad_inquiries"),
        })

    if new_link_requests > 0:
        unit = "request" if new_link_requests == 1 else "requests"
        alerts.append({
            "id": "new-link-requests", "type": "info",
            "perm": "audience.view_membershiplinkrequest",
            "message": f"You have {new_link_requests} membership link {unit}",
            "url": (reverse("dashboard:membership_link_requests")
                    + "?status=NEW"),
        })

    if new_voicemails > 0:
        unit = "voicemail" if new_voicemails == 1 else "voicemails"
        alerts.append({
            "id": "new-voicemails", "type": "info",
            "perm": "phone.view_voicemail",
            "message": f"You have {new_voicemails} new {unit}",
            "url": reverse("dashboard:voicemails") + "?status=NEW",
        })

    if square_pull_status == "FAILED":
        alerts.append({
            "id": "square-pull-failed", "type": "warning",
            "perm": "boxoffice.view_salespull",
            "message": "Yesterday's Square sales pull failed",
        })
    elif square_pull_status == "MISSING":
        alerts.append({
            "id": "square-pull-missing", "type": "warning",
            "perm": "boxoffice.view_salespull",
            "message": "No Square sales pull ran yesterday",
        })
    elif square_pull_status == "INCOMPLETE":
        alerts.append({
            "id": "square-pull-incomplete", "type": "warning",
            "perm": "boxoffice.view_salespull",
            "message": "Yesterday's Square sales pull missed paid online "
                       "ticket orders",
        })

    if square_sync_failures > 0:
        unit = "run" if square_sync_failures == 1 else "runs"
        alerts.append({
            "id": "square-sync-failed", "type": "warning",
            "perm": "cinema.view_engagement",
            "message": f"{square_sync_failures} {unit} failed to sync to Square",
        })

    if square_membership_failures > 0:
        n = square_membership_failures
        if n == 1:
            message = "1 Square membership sale needs attention"
        else:
            message = f"{n} Square membership sales need attention"
        alerts.append({
            "id": "square-membership-failed", "type": "warning",
            "perm": "boxoffice.view_membershipsale",
            "message": message,
            "url": reverse("dashboard:square_sales"),
        })

    if ticket_failures > 0:
        n = ticket_failures
        if n == 1:
            message = "1 online ticket order needs attention"
        else:
            message = f"{n} online ticket orders need attention"
        alerts.append({
            "id": "ticket-failures", "type": "warning",
            "perm": "tickets.view_ticketorder",
            "message": message,
            "url": reverse("dashboard:ticket_orders") + "?status=FAILED",
        })

    for showtime, sold, allowance in nearly_sold_out:
        alerts.append({
            "id": f"nearly-sold-out-{showtime.pk}", "type": "info",
            "perm": "tickets.view_ticketorder",
            "message": (f"{_showing(showtime)} is nearly sold out online "
                        f"({sold} of {allowance})"),
            "url": reverse("dashboard:showtime_orders", args=[showtime.pk]),
        })

    for showtime, count in cancelled_with_orders:
        unit = "order" if count == 1 else "orders"
        alerts.append({
            "id": f"cancelled-orders-{showtime.pk}", "type": "warning",
            "perm": "tickets.view_ticketorder",
            "message": (f"{_showing(showtime)} is cancelled with {count} "
                        f"unrefunded online {unit}"),
            "url": reverse("dashboard:showtime_orders", args=[showtime.pk]),
        })

    return alerts


def _showing(showtime) -> str:
    """'Dune at 7:00 PM', in the cinema's time."""
    starts = format_date(timezone.localtime(showtime.starts_at), "g:i A")
    return f"{showtime.engagement.title} at {starts}"
